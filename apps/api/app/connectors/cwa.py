"""中央氣象署 開放資料平台 connector (opendata.cwa.gov.tw).

Documented datastore endpoints, all behind a free authorization key
(``CWA_API_KEY``):
  - O-A0002-001 自動雨量站-雨量觀測資料 → ``rainfall`` layer
  - W-C0033-001 天氣特報-各別縣市地區目前之天氣警特報情形 → ``official_alert``
  - E-A0015-001 顯著有感地震報告 → ``official_alert`` (earthquake platforms)

Without a key every fetch raises ConnectorDisabled and the layer reports
``disabled`` — we never fabricate weather data.
"""
from __future__ import annotations

from app.connectors.base import (
    ConnectorDisabled,
    ConnectorError,
    feature,
    http_get,
    http_get_json,
    matches_county,
    norm_admin,
    to_float,
    valid_point,
)
from app.core.config import settings
from app.utils.geo import COUNTY_CENTROIDS

SOURCE = "cwa"
HOMEPAGE = "https://opendata.cwa.gov.tw/"
ATTRIBUTION = "中央氣象署 氣象資料開放平台（政府資料開放授權條款）"

RAINFALL_DATASET = "O-A0002-001"
WARNING_DATASET = "W-C0033-001"
EARTHQUAKE_DATASET = "E-A0015-001"


def is_live_enabled() -> bool:
    return bool(settings.CWA_API_KEY)


def _get(dataset: str, extra: dict | None = None) -> dict:
    if not is_live_enabled():
        raise ConnectorDisabled("未設定 CWA_API_KEY（中央氣象署開放資料授權碼）")
    params = {"Authorization": settings.CWA_API_KEY, "format": "JSON", **(extra or {})}
    body = http_get_json(f"{settings.CWA_API_BASE}/{dataset}", params=params)
    if not isinstance(body, dict):
        raise ConnectorDisabled("上游回應格式不符")
    return body


def _missing(v: float | None) -> float | None:
    # CWA encodes missing observations as -99 / -998 / -999
    return None if v is None or v <= -90 else v


def _rain_level(mm_1h: float | None, mm_24h: float | None) -> tuple[str, str]:
    """Classification aligned with CWA 大雨/豪雨 thresholds (24h ≥ 80 大雨,
    ≥ 200 豪雨, ≥ 350 大豪雨, ≥ 500 超大豪雨; 1h ≥ 40 大雨)."""
    h24 = mm_24h or 0.0
    h1 = mm_1h or 0.0
    if h24 >= 500:
        return "extreme", "critical"
    if h24 >= 350:
        return "torrential", "critical"
    if h24 >= 200 or h1 >= 40:
        return "heavy", "high"
    if h24 >= 80:
        return "moderate", "medium"
    return "light", "low"


def map_rainfall(payload: dict, county: str | None) -> list[dict]:
    stations = ((payload or {}).get("records") or {}).get("Station") or []
    out: list[dict] = []
    for st in stations:
        geo = st.get("GeoInfo") or {}
        if county and not matches_county(geo.get("CountyName"), county):
            continue
        lat = lon = None
        for c in geo.get("Coordinates") or []:
            if str(c.get("CoordinateName", "")).upper().startswith("WGS84"):
                lat, lon = to_float(c.get("StationLatitude")), to_float(c.get("StationLongitude"))
        if not valid_point(lat, lon):
            continue
        rain = st.get("RainfallElement") or {}

        def val(key: str) -> float | None:
            return _missing(to_float((rain.get(key) or {}).get("Precipitation")))

        h1, h3, h24 = val("Past1hr"), val("Past3hr"), val("Past24hr")
        level, severity = _rain_level(h1, h24)
        out.append(
            feature(
                id=f"{SOURCE}:rain:{st.get('StationId')}",
                source=SOURCE,
                layer="rainfall",
                lat=lat,  # type: ignore[arg-type]
                lon=lon,  # type: ignore[arg-type]
                properties={
                    "name": st.get("StationName"),
                    "station_id": st.get("StationId"),
                    "county": norm_admin(geo.get("CountyName")),
                    "town": geo.get("TownName"),
                    "rain_now_mm": val("Now"),
                    "rain_1h_mm": h1,
                    "rain_3h_mm": h3,
                    "rain_24h_mm": h24,
                    "level": level,
                    "severity": severity,
                    "status": level,
                    "observed_at": st.get("ObsTime", {}).get("DateTime") if isinstance(st.get("ObsTime"), dict) else st.get("ObsTime"),
                    "updated_at": st.get("ObsTime", {}).get("DateTime") if isinstance(st.get("ObsTime"), dict) else st.get("ObsTime"),
                },
            )
        )
    return out


def map_warnings(payload: dict, county: str | None) -> list[dict]:
    locations = ((payload or {}).get("records") or {}).get("location") or []
    out: list[dict] = []
    for loc in locations:
        name = norm_admin(loc.get("locationName"))
        if county and name != norm_admin(county):
            continue
        centre = COUNTY_CENTROIDS.get(name)
        if centre is None:
            continue
        hazards = ((loc.get("hazardConditions") or {}).get("hazards") or [])
        for idx, hz in enumerate(hazards):
            info = hz.get("info") or {}
            valid = hz.get("validTime") or {}
            phenomena = info.get("phenomena") or ""
            significance = info.get("significance") or ""
            out.append(
                feature(
                    id=f"{SOURCE}:warn:{name}:{idx}",
                    source=SOURCE,
                    layer="official_alert",
                    lat=centre[0],
                    lon=centre[1],
                    properties={
                        "name": f"{phenomena}{significance}".strip() or "天氣特報",
                        "headline": f"{name} {phenomena}{significance}".strip(),
                        "phenomena": phenomena,
                        "significance": significance,
                        "county": name,
                        "valid_from": valid.get("startTime"),
                        "valid_to": valid.get("endTime"),
                        "severity": "high" if "豪雨" in phenomena or "颱風" in phenomena else "medium",
                        "status": "active",
                        "issuer": "中央氣象署",
                        "kind": "weather_warning",
                    },
                )
            )
    return out


def magnitude_to_severity(mag: float | None) -> str:
    if mag is None:
        return "medium"
    if mag >= 6.0:
        return "critical"
    if mag >= 5.0:
        return "high"
    if mag >= 4.0:
        return "medium"
    return "low"


def map_earthquakes(payload: dict) -> list[dict]:
    quakes = ((payload or {}).get("records") or {}).get("Earthquake") or []
    out: list[dict] = []
    for q in quakes:
        info = q.get("EarthquakeInfo") or {}
        epi = info.get("Epicenter") or {}
        lat, lon = to_float(epi.get("EpicenterLatitude")), to_float(epi.get("EpicenterLongitude"))
        if not valid_point(lat, lon):
            continue
        mag = to_float((info.get("EarthquakeMagnitude") or {}).get("MagnitudeValue"))
        out.append(
            feature(
                id=f"{SOURCE}:eq:{q.get('EarthquakeNo')}",
                source=SOURCE,
                layer="official_alert",
                lat=lat,  # type: ignore[arg-type]
                lon=lon,  # type: ignore[arg-type]
                properties={
                    "name": f"規模 {mag} 地震" if mag is not None else "地震報告",
                    "headline": q.get("ReportContent"),
                    "location": epi.get("Location"),
                    "magnitude": mag,
                    "depth_km": to_float(info.get("FocalDepth")),
                    "origin_time": info.get("OriginTime"),
                    "severity": magnitude_to_severity(mag),
                    "status": "active",
                    "issuer": "中央氣象署",
                    "kind": "earthquake",
                },
            )
        )
    return out


def fetch_rainfall(county: str | None) -> list[dict]:
    return map_rainfall(_get(RAINFALL_DATASET), county)


def fetch_warnings(county: str | None) -> list[dict]:
    return map_warnings(_get(WARNING_DATASET), county)


def fetch_earthquakes() -> list[dict]:
    return map_earthquakes(_get(EARTHQUAKE_DATASET))


# representative payloads (shape per CWA docs) — tests only, never served as live data
SAMPLE_RAINFALL: dict = {
    "success": "true",
    "records": {"Station": [
        {"StationName": "廬山", "StationId": "C1I200", "ObsTime": {"DateTime": "2026-08-21T15:00:00+08:00"},
         "GeoInfo": {"Coordinates": [
             {"CoordinateName": "TWD67", "StationLatitude": 24.03, "StationLongitude": 121.17},
             {"CoordinateName": "WGS84", "StationLatitude": 24.0289, "StationLongitude": 121.1761}],
             "CountyName": "南投縣", "TownName": "仁愛鄉"},
         "RainfallElement": {"Now": {"Precipitation": 3.5}, "Past1hr": {"Precipitation": 42.0},
                             "Past3hr": {"Precipitation": 95.5}, "Past24hr": {"Precipitation": 268.0}}},
        {"StationName": "日月潭", "StationId": "467650", "ObsTime": {"DateTime": "2026-08-21T15:00:00+08:00"},
         "GeoInfo": {"Coordinates": [
             {"CoordinateName": "WGS84", "StationLatitude": 23.8813, "StationLongitude": 120.9080}],
             "CountyName": "南投縣", "TownName": "魚池鄉"},
         "RainfallElement": {"Now": {"Precipitation": -99}, "Past1hr": {"Precipitation": 12.5},
                             "Past3hr": {"Precipitation": 30.0}, "Past24hr": {"Precipitation": 96.0}}},
        {"StationName": "板橋", "StationId": "466880", "ObsTime": {"DateTime": "2026-08-21T15:00:00+08:00"},
         "GeoInfo": {"Coordinates": [
             {"CoordinateName": "WGS84", "StationLatitude": 24.9976, "StationLongitude": 121.4420}],
             "CountyName": "新北市", "TownName": "板橋區"},
         "RainfallElement": {"Now": {"Precipitation": 0}, "Past1hr": {"Precipitation": 0},
                             "Past3hr": {"Precipitation": 0}, "Past24hr": {"Precipitation": 2.0}}},
    ]},
}

SAMPLE_WARNINGS: dict = {
    "success": "true",
    "records": {"location": [
        {"locationName": "南投縣", "hazardConditions": {"hazards": [
            {"info": {"phenomena": "豪雨", "significance": "特報"},
             "validTime": {"startTime": "2026-08-21 08:00:00", "endTime": "2026-08-22 08:00:00"}}]}},
        {"locationName": "臺北市", "hazardConditions": {"hazards": []}},
    ]},
}

SAMPLE_EARTHQUAKE: dict = {
    "success": "true",
    "records": {"Earthquake": [
        {"EarthquakeNo": 11410006, "ReportContent": "08/21 08:00 南投縣近郊發生規模 5.2 有感地震",
         "EarthquakeInfo": {"OriginTime": "2026-08-21 08:00:12", "FocalDepth": 18.5,
                            "Epicenter": {"Location": "南投縣政府東北方 12.3 公里", "EpicenterLatitude": 23.98,
                                          "EpicenterLongitude": 120.78},
                            "EarthquakeMagnitude": {"MagnitudeType": "芮氏規模", "MagnitudeValue": 5.2}}},
    ]},
}


# ── radar composite (transparent overlay) ────────────────────────────────
# File API: {CWA_FILE_API_BASE}/{dataset}?Authorization=KEY&downloadType=WEB&format=JSON
# → JSON whose dataset.resource.ProductURL points at the PNG and DateTime is
# the observation time. Frames are kept in memory so the map can replay the
# last ~2 hours; nothing is invented between observations.
import io
import re as _re
import threading as _threading
from collections import deque as _deque

_radar_frames: "_deque[dict]" = _deque(maxlen=24)
_radar_lock = _threading.Lock()


def _find_key(obj, names: tuple[str, ...]):
    """Search for ``names`` in priority order (first name anywhere wins)."""
    for name in names:
        got = _find_one(obj, name)
        if got is not None:
            return got
    return None


def _find_one(obj, name: str):
    if isinstance(obj, dict):
        if name in obj and obj[name] not in (None, ""):
            return obj[name]
        for v in obj.values():
            got = _find_one(v, name)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_one(v, name)
            if got is not None:
                return got
    return None


def _find_key_legacy(obj, names: tuple[str, ...]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in names and v not in (None, ""):
                return v
        for v in obj.values():
            got = _find_key(v, names)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_key(v, names)
            if got is not None:
                return got
    return None


def radar_bounds(body: dict | None = None) -> tuple[float, float, float, float]:
    """(W, S, E, N). Prefer coordinates carried by the response, else the documented extent."""
    if body:
        blob = str(body)
        lons = [float(x) for x in _re.findall(r"[Ll]ongitude[^0-9\-]{0,12}(-?\d+\.?\d*)", blob)]
        lats = [float(x) for x in _re.findall(r"[Ll]atitude[^0-9\-]{0,12}(-?\d+\.?\d*)", blob)]
        lons = [v for v in lons if 100 <= v <= 140]
        lats = [v for v in lats if 10 <= v <= 35]
        if len(lons) >= 2 and len(lats) >= 2:
            return (min(lons), min(lats), max(lons), max(lats))
    w, s_, e, n = (float(v) for v in settings.CWA_RADAR_BOUNDS.split(","))
    return (w, s_, e, n)


def radar_product(body: dict) -> dict:
    url = _find_key(body, ("ProductURL", "productURL", "uri", "URL"))
    if not url or not str(url).lower().startswith("http"):
        raise ConnectorError("雷達回波回應沒有 ProductURL")
    when = _find_key(body, ("DateTime", "dateTime", "ObsTime", "sent"))
    stamp = _re.sub(r"[^0-9]", "", str(when or ""))[:12] or "latest"
    return {"url": str(url), "time": str(when or ""), "stamp": stamp, "bounds": radar_bounds(body)}


def fetch_radar_frames(county: str | None = None) -> list[dict]:
    if not is_live_enabled():
        raise ConnectorDisabled("未設定 CWA_API_KEY（中央氣象署開放資料授權碼）")
    body = http_get_json(
        f"{settings.CWA_FILE_API_BASE}/{settings.CWA_RADAR_DATASET}",
        params={"Authorization": settings.CWA_API_KEY, "downloadType": "WEB", "format": "JSON"},
    )
    if not isinstance(body, dict):
        raise ConnectorError("上游回應格式不符")
    prod = radar_product(body)
    with _radar_lock:
        if not any(f["stamp"] == prod["stamp"] for f in _radar_frames):
            png = http_get(prod["url"], timeout=30).content
            if not png.startswith(b"\x89PNG") and not png[:3] == b"\xff\xd8\xff":
                raise ConnectorError("雷達回波圖檔格式異常")
            png, bounds, fmt = crop_and_shrink(png, prod["bounds"])
            _radar_frames.append({**prod, "bounds": bounds, "bytes": png, "fmt": fmt})
            while len(_radar_frames) > settings.CWA_RADAR_FRAMES:
                _radar_frames.popleft()
        frames = list(_radar_frames)
    w, s_, e, n = frames[-1]["bounds"] if frames else prod["bounds"]
    out = []
    for i, f in enumerate(frames):
        fw, fs, fe, fn = f["bounds"]
        out.append({
            "id": f"{SOURCE}:radar:{f['stamp']}",
            "source": SOURCE,
            "layer": "radar",
            "type": "Raster",
            "coordinates": [[fw, fn], [fe, fn], [fe, fs], [fw, fs]],
            "properties": {
                "name": "雷達整合回波",
                "time": f["time"],
                "stamp": f["stamp"],
                "image_url": f"/v1/public/radar/{f['stamp']}.{f.get('fmt', 'png')}",
                "index": i,
                "frames": len(frames),
                "latest": i == len(frames) - 1,
                "dataset": settings.CWA_RADAR_DATASET,
                "status": "ok",
                "severity": "low",
            },
        })
    return out


def crop_and_shrink(png: bytes, bounds: tuple[float, float, float, float]) -> tuple[bytes, tuple[float, float, float, float], str]:
    """The published composite is 3600×3600 and spans 115–126.5°E; a browser
    decodes that to a ~50 MB texture and re-uploads it on every replay frame.
    Crop to the Taiwan window and downscale — same picture, a fraction of the
    work. Falls back to the original if Pillow is unavailable."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is in requirements
        return png, bounds, "png"
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA")
    except Exception:
        return png, bounds, "png"
    W, H = im.size
    w, s_, e, n = bounds
    try:
        cw, cs, ce, cn = (float(v) for v in settings.CWA_RADAR_CROP.split(","))
    except ValueError:
        return png, bounds, "png"
    cw, ce = max(cw, w), min(ce, e)
    cs, cn = max(cs, s_), min(cn, n)
    if not (cw < ce and cs < cn) or e == w or n == s_:
        return png, bounds, "png"
    x0 = max(0, int((cw - w) / (e - w) * W))
    x1 = min(W, int((ce - w) / (e - w) * W))
    y0 = max(0, int((n - cn) / (n - s_) * H))
    y1 = min(H, int((n - cs) / (n - s_) * H))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return png, bounds, "png"
    im = im.crop((x0, y0, x1, y1))
    cap = settings.CWA_RADAR_MAX_PX
    if max(im.size) > cap:
        ratio = cap / max(im.size)
        im = im.resize((max(1, int(im.width * ratio)), max(1, int(im.height * ratio))), Image.LANCZOS)
    # keep the alpha channel intact — a quantised palette loses the transparent
    # background and paints the whole map. WebP carries alpha at roughly a tenth
    # of PNG's size, which matters because a replay holds several frames.
    buf = io.BytesIO()
    fmt = "webp"
    try:
        im.save(buf, format="WEBP", quality=82, method=4)
    except Exception:
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        fmt = "png"

    # bounds recomputed from the pixels actually kept
    nw = w + x0 / W * (e - w)
    ne = w + x1 / W * (e - w)
    nn = n - y0 / H * (n - s_)
    ns = n - y1 / H * (n - s_)
    return buf.getvalue(), (nw, ns, ne, nn), fmt


def radar_frame_bytes(stamp: str) -> tuple[bytes, str] | None:
    """→ (bytes, media type) for a cached frame."""
    with _radar_lock:
        for f in _radar_frames:
            if f["stamp"] == stamp:
                return f["bytes"], f"image/{f.get('fmt', 'png')}"
    return None


SAMPLE_RADAR_FILE: dict = {
    "cwaopendata": {
        "identifier": "O-A0058-005", "sent": "2026-08-22T12:10:00+08:00",
        "dataset": {"DateTime": "2026-08-22T12:00:00+08:00",
                    "datasetInfo": {"parameterSet": {"parameter": [
                        {"parameterName": "經度範圍", "parameterValue": "115.0-126.5"},
                        {"parameterName": "緯度範圍", "parameterValue": "17.75-29.25"}]}},
                    "resource": {"resourceDesc": "雷達整合回波透明圖層(較大範圍)", "mimeType": "image/png",
                                 "ProductURL": "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Observation/O-A0058-005.png"}},
    }
}
