"""經濟部水利署 水利資料開放平台 connector (public JSON, no key).

Two documented datasets are joined:
  - 河川水位測站站況 (data.gov.tw 22227): station metadata incl. TWD97 x/y,
    river name, address and the three alert levels (一級 = most severe);
  - 即時水位資料 (data.gov.tw 25768): latest water level per station.

Normalised into ``water`` features with a computed alert status.
"""
from __future__ import annotations

from app.connectors.base import feature, http_get_json, matches_county, norm_admin, to_float, valid_point
from app.core.config import settings
from app.utils.geo import centroid_for, parse_twd97_xy, towns_of

SOURCE = "wra"
HOMEPAGE = "https://opendata.wra.gov.tw/"
ATTRIBUTION = "經濟部水利署 水利資料開放平台（政府資料開放授權條款）"


def is_live_enabled() -> bool:
    return True


def _dataset(dataset_id: str) -> list[dict]:
    body = http_get_json(f"{settings.WRA_API_BASE}/{dataset_id}", params={"format": "JSON"}, timeout=40)
    if isinstance(body, dict):
        body = body.get("data") or body.get("records") or []
    return [r for r in body if isinstance(r, dict)]


def fetch_stations() -> list[dict]:
    return _dataset(settings.WRA_STATION_DATASET)


def fetch_levels() -> list[dict]:
    return _dataset(settings.WRA_WATER_LEVEL_DATASET)


def alert_status(level: float | None, a1: float | None, a2: float | None, a3: float | None) -> str:
    """一級警戒 (alert1) is the most severe. Levels are metres above datum."""
    if level is None:
        return "unknown"
    if a1 is not None and level >= a1:
        return "alert1"
    if a2 is not None and level >= a2:
        return "alert2"
    if a3 is not None and level >= a3:
        return "alert3"
    return "normal"


def map_water_levels(stations: list[dict], levels: list[dict], county: str | None) -> list[dict]:
    """Join station metadata with the latest reading. ``stationid`` in the
    real-time feed ('1010H006') is the tail of ``observatoryidentifier``
    ('3132020RV1010H006')."""
    latest: dict[str, dict] = {}
    for row in levels:
        sid = str(row.get("stationid") or "").strip()
        if not sid:
            continue
        prev = latest.get(sid)
        if prev is None or str(row.get("datetime") or "") > str(prev.get("datetime") or ""):
            latest[sid] = row

    out: list[dict] = []
    for st in stations:
        if str(st.get("observationstatus") or "").strip() not in ("", "現存"):
            continue
        ident = str(st.get("observatoryidentifier") or "").strip()
        if not ident:
            continue
        if not matches_county(st.get("locationaddress"), county):
            continue
        point = parse_twd97_xy(st.get("locationbytwd97_xy"))
        if point is None or not valid_point(*point):
            continue
        reading = next((v for k, v in latest.items() if ident.endswith(k)), None)
        level = to_float(reading.get("waterlevel")) if reading else None
        a1, a2, a3 = (to_float(st.get("alertlevel1")), to_float(st.get("alertlevel2")),
                      to_float(st.get("alertlevel3")))
        status = alert_status(level, a1, a2, a3)
        out.append(
            feature(
                id=f"{SOURCE}:{ident}",
                source=SOURCE,
                layer="water",
                lat=point[0],
                lon=point[1],
                properties={
                    "name": str(st.get("observatoryname") or ident).strip(),
                    "river": str(st.get("rivername") or "").strip() or None,
                    "address": str(st.get("locationaddress") or "").strip() or None,
                    "water_level_m": level,
                    "alert_level_1": a1,
                    "alert_level_2": a2,
                    "alert_level_3": a3,
                    "status": status,
                    "severity": {"alert1": "critical", "alert2": "high", "alert3": "medium"}.get(status, "low"),
                    "observed_at": (reading or {}).get("datetime"),
                    "updated_at": (reading or {}).get("datetime"),
                },
            )
        )
    return out


def fetch_water_levels(county: str | None) -> list[dict]:
    return map_water_levels(fetch_stations(), fetch_levels(), county)


SAMPLE_STATIONS: list[dict] = [
    {"observatoryidentifier": "3132020RV1010H006", "observatoryname": "新磺溪橋(即時)", "rivername": "磺溪",
     "locationaddress": "新北市金山區", "alertlevel1": "5.8", "alertlevel2": "4.6", "alertlevel3": "",
     "locationbytwd97_xy": "313411.44 2790930.63", "observationstatus": "現存"},
    {"observatoryidentifier": "1510H049RV", "observatoryname": "愛國橋", "rivername": "烏溪",
     "locationaddress": "南投縣埔里鎮", "alertlevel1": "450.0", "alertlevel2": "449.0", "alertlevel3": "448.0",
     "locationbytwd97_xy": "246900.00 2651000.00", "observationstatus": "現存"},
    {"observatoryidentifier": "3132020RV1010H001", "observatoryname": "金山", "rivername": "磺溪",
     "locationaddress": "新北市金山區金山里", "locationbytwd97_xy": "310928.30 2790168.45",
     "observationstatus": "已廢"},
]
SAMPLE_LEVELS: list[dict] = [
    {"stationid": "1010H006", "datetime": "2026-08-21T16:20:00", "waterlevel": "1.89"},
    {"stationid": "1510H049RV", "datetime": "2026-08-21T16:10:00", "waterlevel": "449.40"},
    {"stationid": "1510H049RV", "datetime": "2026-08-21T16:20:00", "waterlevel": "449.55"},
]


# ── reservoirs ───────────────────────────────────────────────────────────
# 水庫基本資料 (Chinese keys, yearly) joined with 水庫水情資料 (English keys,
# hourly/daily) by reservoir code. No coordinates are published: the marker
# sits at the reservoir's township centre and is flagged ``indicative``.
def fetch_reservoir_basic() -> list[dict]:
    return _dataset(settings.WRA_RESERVOIR_BASIC_DATASET)


def fetch_reservoir_realtime() -> list[dict]:
    return _dataset(settings.WRA_RESERVOIR_REALTIME_DATASET)


def reservoir_status(pct: float | None, spillway: float | None, total_out: float | None, inflow: float | None) -> str:
    if spillway and spillway > 0:
        return "releasing"
    if pct is None:
        return "unknown"
    if pct >= 95:
        return "high"
    if pct < 30:
        return "low"
    return "normal"


def map_reservoirs(basic: list[dict], realtime: list[dict], county: str | None) -> list[dict]:
    latest: dict[str, dict] = {}
    for r in realtime:
        rid = str(r.get("reservoiridentifier") or "").strip()
        if not rid:
            continue
        if rid not in latest or str(r.get("observationtime") or "") > str(latest[rid].get("observationtime") or ""):
            latest[rid] = r
    out: list[dict] = []
    for b in basic:
        rid = str(b.get("水庫代碼") or b.get("reservoiridentifier") or "").strip()
        place = str(b.get("鄉鎮市區名稱") or b.get("townname") or "").replace("\n", "")
        if county and not matches_county(place, county):
            continue
        town = next((t for t in towns_of(county) if t in place), None) if county else None
        ll = centroid_for(county or place[:3], town)
        if ll is None:
            continue
        rt = latest.get(rid, {})
        cap = to_float(str(b.get("目前有效容量") or b.get("currunteffectivecapacity") or "").replace(",", ""))
        eff = to_float(rt.get("effectivewaterstoragecapacity"))
        pct = round(eff / cap * 100, 1) if eff is not None and cap else None
        spill = to_float(rt.get("spillwayoutflow"))
        total_out = to_float(rt.get("totaloutflow"))
        inflow = to_float(rt.get("inflowdischarge"))
        status = reservoir_status(pct, spill, total_out, inflow)
        name = b.get("水庫名稱") or b.get("reservoirname") or rid
        out.append(feature(
            id=f"{SOURCE}:reservoir:{rid}", source=SOURCE, layer="reservoir", lat=ll[0], lon=ll[1],
            properties={
                "name": name,
                "reservoir_id": rid,
                "town": town,
                "agency": b.get("機關名稱") or b.get("agencyname"),
                "river": b.get("河川名稱") or b.get("rivername"),
                "water_level_m": to_float(rt.get("waterlevel")),
                "effective_storage": eff,  # 萬立方公尺
                "effective_capacity": cap,
                "storage_pct": pct,
                "inflow_cms": inflow,
                "outflow_cms": total_out,
                "spillway_cms": spill,
                "rain_mm": to_float(rt.get("accumulaterainfallincatchment")),
                "observed_at": rt.get("observationtime"),
                "updated_at": rt.get("observationtime"),
                "status": status,
                "severity": "high" if status == "releasing" else "medium" if status == "high" else "low",
                "indicative": True,
            },
        ))
    return out


def fetch_reservoirs(county: str | None) -> list[dict]:
    return map_reservoirs(fetch_reservoir_basic(), fetch_reservoir_realtime(), county)


SAMPLE_RESERVOIR_BASIC: list[dict] = [
    {"水庫名稱": "霧社水庫", "水庫代碼": 20501, "鄉鎮市區名稱": "南投縣仁愛鄉", "地區別": "臺灣中區", "機關名稱": "台灣電力股份有限公司", "河川名稱": "濁水溪", "目前有效容量": "3,524.00"},
    {"水庫名稱": "日月潭水庫", "水庫代碼": 20502, "鄉鎮市區名稱": "南投縣魚池鄉", "地區別": "臺灣中區", "機關名稱": "台灣電力股份有限公司", "河川名稱": "濁水溪", "目前有效容量": "12,873.00"},
    {"水庫名稱": "石門水庫", "水庫代碼": 10201, "鄉鎮市區名稱": "桃園市龍潭區、\n大溪區、復興區", "地區別": "臺灣北區", "目前有效容量": "20,000.00"},
]
SAMPLE_RESERVOIR_REALTIME: list[dict] = [
    {"reservoiridentifier": "20501", "observationtime": "2026-08-22T07:00:00", "waterlevel": "1002.3", "effectivewaterstoragecapacity": "3380.5", "spillwayoutflow": "120.0", "inflowdischarge": "260.0", "totaloutflow": "310.0", "accumulaterainfallincatchment": "88.5"},
    {"reservoiridentifier": "20502", "observationtime": "2026-08-22T07:00:00", "waterlevel": "745.1", "effectivewaterstoragecapacity": "9800.0", "spillwayoutflow": "", "inflowdischarge": "", "totaloutflow": ""},
    {"reservoiridentifier": "20502", "observationtime": "2026-08-21T07:00:00", "waterlevel": "744.0", "effectivewaterstoragecapacity": "9700.0"},
]
