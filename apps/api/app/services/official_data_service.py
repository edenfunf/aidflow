"""Official layers: Government API → Connector → Normalizer → GeoFeature →
Map layer. One place decides which connector feeds which layer, caches the
result for a few minutes and turns every failure mode into an explicit
status the UI can show ("尚未設定金鑰" / "上游暫時無法取得").
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.connectors import ardswc, cwa, moi_population, moi_shelters, nantou_open_data, ncdr, taipower, tdx, wra
from app.connectors.base import ConnectorDisabled, ConnectorError
from app.core.config import settings
from app.db.models import Platform
from app.modules import registry


@dataclass(frozen=True)
class ConnectorDef:
    id: str  # == module id
    name: str
    provider: str
    homepage: str
    description: str
    attribution: str
    layers: tuple[str, ...]
    requires_key: bool
    key_env: str | None
    live_enabled: Callable[[], bool]


CONNECTORS: dict[str, ConnectorDef] = {
    "nantou_open_data_connector": ConnectorDef(
        "nantou_open_data_connector", "南投縣政府資料開放平台", "南投縣政府", nantou_open_data.HOMEPAGE,
        "CKAN DataStore：消防局各單位點位。公開資料，無需金鑰。", nantou_open_data.ATTRIBUTION,
        ("fire_station",), False, None, nantou_open_data.is_live_enabled,
    ),
    "moi_shelter_connector": ConnectorDef(
        "moi_shelter_connector", "避難收容處所點位檔", "內政部消防署", moi_shelters.HOMEPAGE,
        "data.gov.tw 73242 全國避難收容處所（依縣市篩選）。公開資料，無需金鑰。", moi_shelters.ATTRIBUTION,
        ("shelter",), False, None, moi_shelters.is_live_enabled,
    ),
    "wra_connector": ConnectorDef(
        "wra_connector", "水利資料開放平台", "經濟部水利署", wra.HOMEPAGE,
        "河川水位測站站況 + 即時水位資料，計算警戒狀態；水庫基本資料 + 水庫水情。公開資料，無需金鑰。", wra.ATTRIBUTION,
        ("water", "reservoir"), False, None, wra.is_live_enabled,
    ),
    "ardswc_connector": ConnectorDef(
        "ardswc_connector", "土石流及大規模崩塌防災資訊網", "農業部農村發展及水土保持署", ardswc.HOMEPAGE,
        "土石流潛勢溪流、影響範圍、大規模崩塌潛勢區（年度圖資）＋ 紅黃警戒（即時 JSON）。公開資料，無需金鑰。", ardswc.ATTRIBUTION,
        ("debris_flow", "landslide_zone"), False, None, ardswc.is_live_enabled,
    ),
    "tdx_connector": ConnectorDef(
        "tdx_connector", "TDX 運輸資料流通服務", "交通部", tdx.HOMEPAGE,
        "路況 CCTV（縣市＋公路局）與路況消息（封閉、坍方、施工）。需 TDX 會員金鑰。", tdx.ATTRIBUTION,
        ("road_traffic",), True, "TDX_CLIENT_ID", tdx.is_live_enabled,
    ),
    "moi_population_connector": ConnectorDef(
        "moi_population_connector", "戶政司人口統計", "內政部", moi_population.HOMEPAGE,
        "各村里人口數（ODRP013）彙整到鄉鎮，用於受影響人口估算。公開資料，無需金鑰。", moi_population.ATTRIBUTION,
        ("population",), False, None, moi_population.is_live_enabled,
    ),
    "taipower_connector": ConnectorDef(
        "taipower_connector", "台電計畫性工作停電", "台灣電力公司", taipower.HOMEPAGE,
        "每日計畫性停電公告（data.gov.tw 26144），依鄉鎮彙整。台電未開放事故停電即時資料。", taipower.ATTRIBUTION,
        ("power_outage",), False, None, taipower.is_live_enabled,
    ),
    "cwa_connector": ConnectorDef(
        "cwa_connector", "氣象資料開放平台", "中央氣象署", cwa.HOMEPAGE,
        "自動雨量站觀測（O-A0002-001）、天氣特報（W-C0033-001）、地震報告（E-A0015-001）、雷達整合回波透明圖層（O-A0058-005）。", cwa.ATTRIBUTION,
        ("rainfall", "official_alert", "radar"), True, "CWA_API_KEY", cwa.is_live_enabled,
    ),
    "ncdr_connector": ConnectorDef(
        "ncdr_connector", "民生示警公開資料平台 (CAP)", "國家災害防救科技中心", ncdr.HOMEPAGE,
        "CAP 1.2 多災害示警；需平台會員授權的 feed URL。", ncdr.ATTRIBUTION,
        ("official_alert",), True, "NCDR_CAP_FEED_URL", ncdr.is_live_enabled,
    ),
}

# layer -> ordered list of (connector id, fetch(county) -> features)
_LAYER_FETCHERS: dict[str, list[tuple[str, Callable[[str | None], list[dict]]]]] = {
    "shelter": [("moi_shelter_connector", moi_shelters.fetch_shelters)],
    "fire_station": [("nantou_open_data_connector", lambda county: nantou_open_data.fetch_fire_stations())],
    "water": [("wra_connector", wra.fetch_water_levels)],
    "rainfall": [("cwa_connector", cwa.fetch_rainfall)],
    "official_alert": [("cwa_connector", cwa.fetch_warnings), ("ncdr_connector", ncdr.fetch_cap)],
    "radar": [("cwa_connector", cwa.fetch_radar_frames)],
    "debris_flow": [("ardswc_connector", ardswc.fetch_debris_flow)],
    "landslide_zone": [("ardswc_connector", ardswc.fetch_landslide_zones)],
    "road_traffic": [("tdx_connector", tdx.fetch_road_traffic)],
    "reservoir": [("wra_connector", wra.fetch_reservoirs)],
    "population": [("moi_population_connector", moi_population.fetch_population)],
    "power_outage": [("taipower_connector", taipower.fetch_outages)],
}

OFFICIAL_LAYERS = tuple(_LAYER_FETCHERS.keys())


@dataclass
class _CacheEntry:
    value: dict
    expires_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)


_cache: dict[str, _CacheEntry] = {}
_cache_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_layer(layer: str, county: str | None, hazards: list[str]) -> dict:
    fetchers = _LAYER_FETCHERS.get(layer)
    if not fetchers:
        return {"layer": layer, "source": "none", "status": "unsupported", "detail": "不是官方資料圖層",
                "features": [], "count": 0, "fetched_at": _now_iso()}
    features: list[dict] = []
    statuses: list[str] = []
    details: list[str] = []
    sources: list[str] = []
    attribution: list[str] = []
    for cid, fn in fetchers:
        cdef = CONNECTORS[cid]
        try:
            got = fn(county)
            features.extend(got)
            statuses.append("ok")
            sources.append(cid)
            attribution.append(cdef.attribution)
        except ConnectorDisabled as exc:
            statuses.append("disabled")
            details.append(f"{cdef.name}：{exc.reason}")
        except ConnectorError as exc:
            statuses.append("unavailable")
            details.append(f"{cdef.name}：{exc.reason}")
        except Exception as exc:  # noqa: BLE001 — an unexpected upstream shape must not 500 the map
            statuses.append("unavailable")
            details.append(f"{cdef.name}：資料格式異常（{exc.__class__.__name__}）")
    if layer == "official_alert" and "earthquake" in hazards and cwa.is_live_enabled():
        try:
            features.extend(cwa.fetch_earthquakes())
        except (ConnectorDisabled, ConnectorError) as exc:
            details.append(f"中央氣象署地震報告：{exc.reason}")
    if "ok" in statuses:
        status = "ok"
    elif "unavailable" in statuses:
        status = "unavailable"
    else:
        status = "disabled"
    return {
        "layer": layer,
        "source": "+".join(sources) if sources else fetchers[0][0],
        "status": status,
        "detail": "；".join(details) or None,
        "attribution": "；".join(dict.fromkeys(attribution)) or None,
        "fetched_at": _now_iso(),
        "cached": False,
        "count": len(features),
        "features": features,
    }


def get_layer(platform: Platform, layer: str, *, force: bool = False) -> dict:
    """Cached per (layer, county). Errors are cached briefly too so a dead
    upstream is not hammered on every page load."""
    if layer not in (platform.layers or []):
        return {"layer": layer, "source": "none", "status": "not_enabled", "detail": "此平台未啟用該圖層",
                "features": [], "count": 0, "fetched_at": _now_iso(), "cached": False}
    key = f"{layer}|{platform.county or ''}|{','.join(platform.hazards or [])}"
    ttl = settings.OFFICIAL_DATA_CACHE_SECONDS
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            entry = _cache[key] = _CacheEntry(value={}, expires_at=0.0)
    with entry.lock:
        if not force and entry.value and entry.expires_at > time.monotonic():
            return {**entry.value, "cached": True}
        value = _fetch_layer(layer, platform.county, list(platform.hazards or []))
        entry.value = value
        entry.expires_at = time.monotonic() + (ttl if value["status"] == "ok" else min(ttl, 60))
        return value


def layer_statuses(platform: Platform) -> list[dict]:
    """Status of every enabled layer without fetching the heavy ones."""
    out: list[dict] = []
    for key in platform.layers or []:
        spec = registry.layer_by_key(key)
        if spec is None:
            continue
        if key in _LAYER_FETCHERS:
            cids = [cid for cid, _ in _LAYER_FETCHERS[key]]
            live = [cid for cid in cids if CONNECTORS[cid].live_enabled()]
            cached = None
            with _cache_lock:
                for ck, entry in _cache.items():
                    if ck.startswith(f"{key}|{platform.county or ''}|"):
                        cached = entry.value or None
            if cached:
                status, detail = cached["status"], cached.get("detail")
            elif live:
                status, detail = "ready", None
            else:
                status = "disabled"
                detail = "；".join(
                    f"需設定 {CONNECTORS[cid].key_env}" for cid in cids if CONNECTORS[cid].key_env
                ) or "未設定來源"
            out.append({"layer": key, "module_id": spec.id, "name": spec.name, "kind": "official",
                        "source": "+".join(cids), "status": status, "detail": detail})
        else:
            out.append({"layer": key, "module_id": spec.id, "name": spec.name, "kind": "internal",
                        "source": None, "status": "ok", "detail": None})
    return out


def connector_statuses() -> list[dict]:
    out = []
    for c in CONNECTORS.values():
        live = c.live_enabled()
        out.append({
            "id": c.id,
            "name": c.name,
            "provider": c.provider,
            "homepage": c.homepage,
            "description": c.description,
            "layers": list(c.layers),
            "requires_key": c.requires_key,
            "key_env": c.key_env,
            "live_enabled": live,
            "status": "ready" if live else "disabled",
            "detail": None if live else f"未設定 {c.key_env}，圖層將顯示為不可用（graceful fallback）",
        })
    return out


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
