"""南投縣政府資料開放平台 (CKAN) connector.

Uses the documented CKAN Action API ``datastore_search`` on resources that are
DataStore-active. Currently wired: 南投縣消防局各單位地圖 (fire units with
緯度/經度) → ``fire_station`` layer. Public, no key.
"""
from __future__ import annotations

from app.connectors.base import ConnectorError, feature, http_get_json, to_float, valid_point
from app.core.config import settings

SOURCE = "nantou_open_data"
HOMEPAGE = "https://data.nantou.gov.tw/"
ATTRIBUTION = "南投縣政府資料開放平台（政府資料開放授權條款）"


def is_live_enabled() -> bool:
    return True  # public CKAN, no credential


def datastore_search(resource_id: str, *, limit: int = 1000) -> list[dict]:
    body = http_get_json(
        f"{settings.NANTOU_CKAN_BASE}/datastore_search",
        params={"resource_id": resource_id, "limit": limit},
    )
    if not isinstance(body, dict) or not body.get("success"):
        raise ConnectorError("CKAN datastore_search 回應失敗")
    return list((body.get("result") or {}).get("records") or [])


def map_fire_stations(records: list[dict]) -> list[dict]:
    """CKAN records {單位, 地址, 電話, 緯度, 經度} -> fire_station features."""
    out: list[dict] = []
    for idx, rec in enumerate(records):
        lat = to_float(rec.get("緯度"))
        lon = to_float(rec.get("經度"))
        if not valid_point(lat, lon):
            continue
        name = str(rec.get("單位") or "").strip() or f"消防單位 {idx + 1}"
        out.append(
            feature(
                id=f"{SOURCE}:fire:{rec.get('_id', idx)}",
                source=SOURCE,
                layer="fire_station",
                lat=lat,  # type: ignore[arg-type]
                lon=lon,  # type: ignore[arg-type]
                properties={
                    "name": name,
                    "address": str(rec.get("地址") or "").strip() or None,
                    "phone": str(rec.get("電話") or "").strip() or None,
                    "kind": "大隊" if "大隊" in name else "分隊",
                    "status": "active",
                },
            )
        )
    return out


def fetch_fire_stations() -> list[dict]:
    return map_fire_stations(datastore_search(settings.NANTOU_FIRE_STATION_RESOURCE))


# representative DataStore records (shape per the live resource) for tests
SAMPLE_FIRE_STATIONS: list[dict] = [
    {"_id": 1, "單位": "第一大隊", "地址": "南投市南營路810號", "電話": "(049)2351119",
     "緯度": "23.945575", "經度": "120.679225"},
    {"_id": 2, "單位": "南投分隊", "地址": "南投縣南投市民族路494號", "電話": "(049)2222534",
     "緯度": "23.906865", "經度": "120.680071"},
    {"_id": 3, "單位": "無座標分隊", "地址": "—", "電話": "", "緯度": "", "經度": None},
]
