"""農業部農村發展及水土保持署 (ARDSWC) connector — debris-flow potential
streams, their impact ranges, large-scale landslide susceptibility zones and
the live red/yellow alerts that are issued against them.

Sources (all public, no key):
  - alerts (JSON, live):  https://ls.ardswc.gov.tw/api/LandSlideAlertOpenData
      (the documented 246.ardswc.gov.tw/webService/GetAlertData.ashx now
       redirects here). Fields: AlertType D=土石流 / L=大規模崩塌, DebrisNo,
       LandslideID / LSNo, County, Town, Vill, AlertLevel y|r, LastUpdateDate.
  - potential streams  (data.gov.tw 176524, SHP, TWD97 TM2) — 1,753 polylines
  - impact ranges      (data.gov.tw 176526, SHP, TWD97 TM2) — polygons + overflow point
  - landslide zones    (data.gov.tw 176527, SHP, TWD97 TM2) — 94 polygons

The shapefiles are official annual products: they are downloaded once,
cached on disk for ``OFFICIAL_FILE_CACHE_DAYS`` and converted to WGS84
GeoFeatures in memory. Alerts are joined by stream / zone number so the map
can show *which* stream is under warning, not just which township.
"""
from __future__ import annotations

import io
import threading
import time
import zipfile
from pathlib import Path

from app.connectors.base import ConnectorError, feature, http_get, http_get_json, matches_county, polygon_feature
from app.core.config import settings
from app.utils.geo import simplify_line, twd97_to_wgs84

SOURCE = "ardswc"
HOMEPAGE = "https://246.ardswc.gov.tw/"
ATTRIBUTION = "農業部農村發展及水土保持署 土石流及大規模崩塌防災資訊網（政府資料開放授權條款）"

RISK_SEVERITY = {"高": "high", "中": "medium", "低": "low", "持續觀察": "low"}
ALERT_LEVEL = {"r": "red", "y": "yellow"}


def is_live_enabled() -> bool:
    return True


# ── alerts ───────────────────────────────────────────────────────────────
def fetch_alerts() -> list[dict]:
    body = http_get_json(settings.ARDSWC_ALERT_URL, timeout=20)
    if not isinstance(body, list):
        raise ConnectorError("警戒資料格式不符")
    return [r for r in body if isinstance(r, dict)]


def index_alerts(rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """→ (by debris-flow stream number, by landslide zone number)."""
    by_stream: dict[str, dict] = {}
    by_zone: dict[str, dict] = {}
    for r in rows:
        level = ALERT_LEVEL.get(str(r.get("AlertLevel") or "").lower())
        if not level:
            continue
        rec = {"alert": level, "alert_time": r.get("LastUpdateDate"), "report_id": r.get("ReportID"),
               "county": r.get("County"), "town": r.get("Town"), "vill": r.get("Vill")}
        if str(r.get("AlertType") or "").upper() == "L":
            for key in (r.get("LSNo"), r.get("LandslideID")):
                if key and key != "-":
                    by_zone[str(key).strip()] = rec
        else:
            key = str(r.get("DebrisNo") or "").strip()
            if key and key != "-":
                # red beats yellow when the same stream appears twice
                if key not in by_stream or (level == "red" and by_stream[key]["alert"] != "red"):
                    by_stream[key] = rec
    return by_stream, by_zone


# ── shapefiles (cached on disk, parsed once per process) ─────────────────
_shape_cache: dict[str, tuple[float, list[dict]]] = {}
_shape_lock = threading.Lock()


def _cache_dir() -> Path:
    p = Path(settings.MEDIA_ROOT) / "official-cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _download(url: str, name: str) -> bytes:
    path = _cache_dir() / f"{name}.zip"
    max_age = settings.OFFICIAL_FILE_CACHE_DAYS * 86400
    if path.exists() and time.time() - path.stat().st_mtime < max_age and path.stat().st_size > 1000:
        return path.read_bytes()
    resp = http_get(url, timeout=180)
    data = resp.content
    if not data.startswith(b"PK"):
        raise ConnectorError("下載的圖資不是 ZIP 檔")
    path.write_bytes(data)
    return data


def read_shapefile(data: bytes) -> tuple[list[dict], str]:
    """Parse a zipped shapefile → list of {record, geometry(WGS84 rings)}.
    Geometry is returned as a list of parts; each part is [[lon, lat], ...]."""
    import shapefile  # pyshp, pure python

    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    shp = next((n for n in names if n.lower().endswith(".shp")), None)
    if not shp:
        raise ConnectorError("ZIP 內沒有 .shp")
    base = shp[:-4]
    enc = "utf-8"
    if base + ".cpg" in names:
        enc = z.read(base + ".cpg").decode("ascii", "ignore").strip() or "utf-8"
    r = shapefile.Reader(
        shp=io.BytesIO(z.read(shp)), dbf=io.BytesIO(z.read(base + ".dbf")),
        shx=io.BytesIO(z.read(base + ".shx")) if base + ".shx" in names else None,
        encoding=enc, encodingErrors="replace",
    )
    out: list[dict] = []
    for sr in r.iterShapeRecords():
        pts = sr.shape.points
        parts = list(sr.shape.parts) + [len(pts)]
        rings = []
        for a, b in zip(parts[:-1], parts[1:]):
            ring = []
            for x, y in pts[a:b]:
                lat, lon = twd97_to_wgs84(x, y)
                ring.append([round(lon, 6), round(lat, 6)])
            if len(ring) >= 2:
                # annual survey geometry is far finer than any map scale needs;
                # every extra vertex is bytes on the wire and work in the browser
                rings.append(simplify_line(ring, tolerance_deg=0.00025, max_points=140))
        out.append({"record": sr.record.as_dict(), "parts": rings, "shape_type": r.shapeTypeName})
    return out, r.shapeTypeName


def _shapes(kind: str) -> list[dict]:
    url = {
        "streams": settings.ARDSWC_STREAM_SHP_URL,
        "impact": settings.ARDSWC_IMPACT_SHP_URL,
        "landslide": settings.ARDSWC_LANDSLIDE_SHP_URL,
    }[kind]
    with _shape_lock:
        hit = _shape_cache.get(kind)
        if hit and time.monotonic() - hit[0] < settings.OFFICIAL_FILE_CACHE_DAYS * 86400:
            return hit[1]
        rows, _ = read_shapefile(_download(url, f"ardswc-{kind}"))
        _shape_cache[kind] = (time.monotonic(), rows)
        return rows


def clear_shape_cache() -> None:
    with _shape_lock:
        _shape_cache.clear()


# ── normalisers (pure) ───────────────────────────────────────────────────
def _sev(risk: str | None, alert: str | None) -> str:
    if alert == "red":
        return "critical"
    if alert == "yellow":
        return "high"
    return RISK_SEVERITY.get(str(risk or "").strip(), "low")


def map_streams(rows: list[dict], alerts_by_stream: dict[str, dict], county: str | None) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        rec = row["record"]
        if county and not (matches_county(rec.get("County01"), county) or matches_county(rec.get("County02"), county)):
            continue
        no = str(rec.get("Debrisno") or "").strip()
        alert = alerts_by_stream.get(no)
        coords = row["parts"][0] if row["parts"] else []
        if len(coords) < 2:
            continue
        props = {
            "name": rec.get("Name") or no,
            "debris_no": no,
            "county": rec.get("County01"),
            "town": rec.get("Town01"),
            "vill": rec.get("Vill01"),
            "landmark": rec.get("Mark"),
            "road": rec.get("Roadname"),
            "households_class": rec.get("TRes_Class"),
            "risk": rec.get("Risk"),
            "length_km": rec.get("Length"),
            "basin": rec.get("Basin"),
            "year": rec.get("Year"),
            "alert": alert["alert"] if alert else None,
            "alert_time": alert["alert_time"] if alert else None,
            "severity": _sev(rec.get("Risk"), alert["alert"] if alert else None),
            "status": (alert["alert"] if alert else "potential"),
            "kind": "stream",
        }
        out.append({"id": f"{SOURCE}:stream:{no}", "source": SOURCE, "layer": "debris_flow", "type": "LineString",
                    "coordinates": coords, "properties": props})
    return out


def map_impact_ranges(rows: list[dict], alerts_by_stream: dict[str, dict], county: str | None) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        rec = row["record"]
        if county and not matches_county(rec.get("County"), county):
            continue
        if not row["parts"]:
            continue
        no = str(rec.get("Debrisno") or "").strip()
        alert = alerts_by_stream.get(no)
        out.append(polygon_feature(
            id=f"{SOURCE}:impact:{no}:{rec.get('Overflowno')}", source=SOURCE, layer="debris_flow",
            rings=row["parts"],
            properties={
                "name": f"{no} 影響範圍",
                "debris_no": no,
                "town": rec.get("Town"),
                "vill": rec.get("Vill"),
                "address": rec.get("Address"),
                "households": rec.get("Total_Res"),
                "households_class": rec.get("Res_Class"),
                "risk": rec.get("Risk"),
                "alert": alert["alert"] if alert else None,
                "severity": _sev(rec.get("Risk"), alert["alert"] if alert else None),
                "status": (alert["alert"] if alert else "potential"),
                "kind": "impact",
            },
        ))
    return out


def map_landslide_zones(rows: list[dict], alerts_by_zone: dict[str, dict], county: str | None) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        rec = row["record"]
        if county and not (matches_county(rec.get("County01"), county) or matches_county(rec.get("County02"), county)):
            continue
        if not row["parts"]:
            continue
        no = str(rec.get("lslno") or rec.get("Lslno") or "").strip()
        alert = alerts_by_zone.get(no)
        out.append(polygon_feature(
            id=f"{SOURCE}:zone:{no}", source=SOURCE, layer="landslide_zone", rings=row["parts"],
            properties={
                "name": rec.get("Name") or no,
                "zone_no": no,
                "county": rec.get("County01"),
                "town": rec.get("Town01"),
                "vill": rec.get("Vill01"),
                "landmark": rec.get("Mark"),
                "road": rec.get("Roadname"),
                "hazard_type": rec.get("Type"),
                "households": rec.get("Dw_count"),
                "households_class": rec.get("TRes_Class"),
                "area_ha": rec.get("P_area"),
                "risk": rec.get("Risk"),
                "alert": alert["alert"] if alert else None,
                "alert_time": alert["alert_time"] if alert else None,
                "severity": _sev(rec.get("Risk"), alert["alert"] if alert else None),
                "status": (alert["alert"] if alert else "potential"),
                "kind": "zone",
            },
        ))
    return out


def map_alert_points(rows: list[dict], county: str | None) -> list[dict]:
    """Township-level alert markers for alerts whose stream is not in the
    shapefile (e.g. a newly numbered stream) — positioned at the township."""
    from app.utils.geo import centroid_for

    out: list[dict] = []
    for r in rows:
        level = ALERT_LEVEL.get(str(r.get("AlertLevel") or "").lower())
        if not level or (county and not matches_county(r.get("County"), county)):
            continue
        ll = centroid_for(r.get("County"), r.get("Town"))
        if ll is None:
            continue
        key = r.get("DebrisNo") if str(r.get("AlertType") or "").upper() != "L" else (r.get("LSNo") or r.get("LandslideID"))
        out.append(feature(
            id=f"{SOURCE}:alert:{key}", source=SOURCE, layer="debris_flow", lat=ll[0], lon=ll[1],
            properties={"name": f"{r.get('Town') or ''} {'紅色' if level == 'red' else '黃色'}警戒", "alert": level,
                        "alert_time": r.get("LastUpdateDate"), "debris_no": key, "town": r.get("Town"),
                        "vill": r.get("Vill"), "severity": "critical" if level == "red" else "high",
                        "status": level, "kind": "alert", "indicative": True},
        ))
    return out


# ── live fetchers ────────────────────────────────────────────────────────
def _alerts_safe() -> list[dict]:
    try:
        return fetch_alerts()
    except ConnectorError:
        return []  # the potential map is still valid without live alerts


def fetch_debris_flow(county: str | None) -> list[dict]:
    alerts = _alerts_safe()
    by_stream, _ = index_alerts(alerts)
    feats = map_streams(_shapes("streams"), by_stream, county)
    known = {f["properties"]["debris_no"] for f in feats}
    try:
        feats += map_impact_ranges(_shapes("impact"), by_stream, county)
    except ConnectorError:
        pass  # impact polygons are a refinement; streams alone are still useful
    feats += [f for f in map_alert_points(alerts, county)
              if str(f["properties"].get("debris_no")) not in known and not str(f["id"]).endswith(":None")]
    return feats


def fetch_landslide_zones(county: str | None) -> list[dict]:
    _, by_zone = index_alerts(_alerts_safe())
    return map_landslide_zones(_shapes("landslide"), by_zone, county)


# representative payloads — tests only
SAMPLE_ALERTS: list[dict] = [
    {"AlertType": "D", "DebrisNo": "投縣DF124", "LandslideID": "-", "LandslideName": "-", "County": "南投縣", "Town": "中寮鄉",
     "Vill": "和興村", "AlertLevel": "r", "LastUpdateDate": "2026-08-22 12:01", "ReportID": "115I-2-0", "LSNo": "-"},
    {"AlertType": "D", "DebrisNo": "投縣DF001", "County": "南投縣", "Town": "仁愛鄉", "Vill": "親愛村", "AlertLevel": "y",
     "LastUpdateDate": "2026-08-22 12:01", "ReportID": "115I-2-0"},
    {"AlertType": "L", "DebrisNo": "-", "LandslideID": "DS145", "LandslideName": "高雄市-六龜區-T001(藤枝林道3.5K)",
     "County": "高雄市", "Town": "六龜區", "Vill": None, "AlertLevel": "r", "LastUpdateDate": "2026-08-22 12:01", "LSNo": "高市LL003"},
]
SAMPLE_STREAM_ROWS: list[dict] = [
    {"record": {"Debrisno": "投縣DF124", "County01": "南投縣", "Town01": "中寮鄉", "Vill01": "和興村", "Name": "平林溪支流",
                "Mark": "炭寮橋", "Roadname": "投26線", "TRes_Class": "1~4戶", "Risk": "中", "Length": 0.751, "Basin": "烏溪", "Year": 115},
     "parts": [[[120.7660, 23.8790], [120.7700, 23.8820], [120.7740, 23.8860]]], "shape_type": "POLYLINE"},
    {"record": {"Debrisno": "宜縣DF135", "County01": "宜蘭縣", "Town01": "三星鄉", "Vill01": "天山村", "Name": "蘭陽溪中游",
                "Mark": "天山農場", "Roadname": "台7丙線", "TRes_Class": "1~4戶", "Risk": "低", "Length": 0.696},
     "parts": [[[121.60, 24.65], [121.61, 24.66]]], "shape_type": "POLYLINE"},
]
SAMPLE_ZONE_ROWS: list[dict] = [
    {"record": {"lslno": "投縣LL001", "County01": "南投縣", "Town01": "仁愛鄉", "Vill01": "親愛村", "Name": "親愛村大規模崩塌潛勢區",
                "Type": "崩塌", "Dw_count": 12, "TRes_Class": "5~50戶", "Risk": "高", "P_area": 35.2},
     "parts": [[[121.12, 23.94], [121.13, 23.94], [121.13, 23.95], [121.12, 23.95], [121.12, 23.94]]], "shape_type": "POLYGON"},
]
