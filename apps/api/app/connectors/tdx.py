"""交通部 TDX 運輸資料流通服務 connector — road CCTV cameras and road
news/events for the platform's county.

Documented (路況資訊 v2 OAS, tdx.transportdata.tw):
  - token:  POST https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token
            grant_type=client_credentials (client id / secret from the TDX member centre)
  - CCTV:   GET /api/basic/v2/Road/Traffic/CCTV/City/{City}   and   /CCTV/Highway (公路局)
            fields: CCTVID, VideoStreamURL, VideoImageURL, PositionLat/Lon, RoadName,
            SurveillanceDescription, RoadSection, LocationMile
  - news:   GET /api/basic/v2/Road/Traffic/Live/News/City/{City} and /News/Highway
            fields: NewsID, Title, NewsCategory, Description, StartTime, EndTime, PublishTime
            (no coordinates — shown as a feed, matched to the county by text)

Without ``TDX_CLIENT_ID`` / ``TDX_CLIENT_SECRET`` the layer reports ``disabled``.
"""
from __future__ import annotations

import threading
import time

import httpx

from app.connectors.base import ConnectorDisabled, ConnectorError, _CTX, feature, to_float, valid_point
from app.core.config import settings
from app.utils.geo import COUNTY_CENTROIDS, normalize_admin, towns_of

SOURCE = "tdx"
HOMEPAGE = "https://tdx.transportdata.tw/"
ATTRIBUTION = "交通部 TDX 運輸資料流通服務（政府資料開放授權條款）"
TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"

# TDX City enum (路況資訊 v2)
CITY_CODES: dict[str, str] = {
    "宜蘭縣": "YilanCounty", "新竹縣": "HsinchuCounty", "彰化縣": "ChanghuaCounty", "南投縣": "NantouCounty",
    "雲林縣": "YunlinCounty", "屏東縣": "PingtungCounty", "臺東縣": "TaitungCounty", "基隆市": "Keelung",
    "新竹市": "Hsinchu", "嘉義市": "Chiayi", "臺北市": "Taipei", "高雄市": "Kaohsiung", "新北市": "NewTaipei",
    "臺中市": "Taichung", "臺南市": "Tainan", "桃園市": "Taoyuan", "金門縣": "KinmenCounty",
}
# approximate county extents used to pick 公路局 cameras that sit in the county
COUNTY_BBOX: dict[str, tuple[float, float, float, float]] = {  # lat_min, lat_max, lon_min, lon_max
    "南投縣": (23.45, 24.30, 120.60, 121.40),
}


def is_live_enabled() -> bool:
    return bool(settings.TDX_CLIENT_ID and settings.TDX_CLIENT_SECRET)


_token: dict = {"value": None, "expires": 0.0}
_token_lock = threading.Lock()


def _access_token() -> str:
    if not is_live_enabled():
        raise ConnectorDisabled("未設定 TDX_CLIENT_ID / TDX_CLIENT_SECRET（交通部 TDX 會員金鑰）")
    with _token_lock:
        if _token["value"] and time.time() < _token["expires"] - 60:
            return _token["value"]
        try:
            resp = httpx.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials", "client_id": settings.TDX_CLIENT_ID,
                      "client_secret": settings.TDX_CLIENT_SECRET},
                timeout=settings.OFFICIAL_DATA_TIMEOUT_SECONDS, verify=_CTX,
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(f"TDX 取得權杖失敗：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ConnectorError(f"TDX 權杖回應 HTTP {resp.status_code}")
        body = resp.json()
        _token["value"] = body.get("access_token")
        _token["expires"] = time.time() + float(body.get("expires_in") or 3600)
        if not _token["value"]:
            raise ConnectorError("TDX 權杖回應缺少 access_token")
        return _token["value"]


def _get(path: str, params: dict | None = None) -> dict | list:
    token = _access_token()
    try:
        resp = httpx.get(
            f"{settings.TDX_API_BASE}{path}", params={"$format": "JSON", **(params or {})},
            headers={"authorization": f"Bearer {token}", "Accept-Encoding": "gzip"},
            timeout=max(60.0, float(settings.OFFICIAL_DATA_TIMEOUT_SECONDS)), verify=_CTX,  # the nationwide CCTV list is large
        )
    except httpx.HTTPError as exc:
        raise ConnectorError(f"連線失敗：{exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise ConnectorError(f"上游回應 HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ConnectorError("上游回應不是有效的 JSON") from exc


def _city(county: str | None) -> str | None:
    name = normalize_admin(county)
    return CITY_CODES.get(name) or CITY_CODES.get(name.replace("台", "臺")) or CITY_CODES.get(name.replace("臺", "台"))


def _in_county(lat: float, lon: float, county: str | None) -> bool:
    """Inside the county's rough extent *and* within 15 km of one of its
    township centres — the second test keeps Taichung's cameras out of the
    Nantou picture without needing a boundary file."""
    from app.utils.geo import TOWN_CENTROIDS, haversine_m

    name = normalize_admin(county)
    box = COUNTY_BBOX.get(name)
    if box is not None and not (box[0] <= lat <= box[1] and box[2] <= lon <= box[3]):
        return False
    towns = TOWN_CENTROIDS.get(name)
    if not towns:
        return True
    return any(haversine_m(lat, lon, t[0], t[1]) <= 15000 for t in towns.values())


# ── normalisers (pure) ───────────────────────────────────────────────────
def map_cctv(payload: dict | list, county: str | None, authority: str) -> list[dict]:
    cams = payload.get("CCTVs") if isinstance(payload, dict) else payload
    out: list[dict] = []
    for c in cams or []:
        lat, lon = to_float(c.get("PositionLat")), to_float(c.get("PositionLon"))
        if not valid_point(lat, lon) or not _in_county(lat, lon, county):  # type: ignore[arg-type]
            continue
        road = c.get("RoadName") or ""
        desc = c.get("SurveillanceDescription") or c.get("RoadSection") or ""
        out.append(feature(
            id=f"{SOURCE}:cctv:{c.get('CCTVID')}", source=SOURCE, layer="road_traffic", lat=lat, lon=lon,  # type: ignore[arg-type]
            properties={
                "name": f"{road} {desc}".strip() or str(c.get("CCTVID")),
                "cctv_id": c.get("CCTVID"),
                "road": road,
                "description": desc,
                "mile": c.get("LocationMile"),
                "image_url": c.get("VideoImageURL"),
                "stream_url": c.get("VideoStreamURL"),
                "refresh_s": c.get("ImageRefreshRate"),
                "authority": authority,
                "kind": "cctv",
                "status": "live",
                "severity": "low",
            },
        ))
    return out


def map_news(payload: dict | list, county: str | None, authority: str) -> list[dict]:
    items = payload.get("Newses") if isinstance(payload, dict) else payload
    centre = COUNTY_CENTROIDS.get(normalize_admin(county)) if county else None
    names = [normalize_admin(county)] + towns_of(county) if county else []
    out: list[dict] = []
    for n in items or []:
        text = f"{n.get('Title') or ''} {n.get('Description') or ''}"
        if authority != "city" and names and not any(nm and nm in text for nm in names):
            continue  # 公路局 posts nationwide: keep only what names this county or its towns
        title = n.get("Title") or "路況消息"
        cat = str(n.get("NewsCategory") or "")
        severe = any(k in text for k in ("封閉", "中斷", "坍方", "落石", "禁止通行", "土石"))
        out.append(feature(
            id=f"{SOURCE}:news:{n.get('NewsID')}", source=SOURCE, layer="road_traffic",
            lat=centre[0] if centre else 0.0, lon=centre[1] if centre else 0.0,
            properties={
                "name": title,
                "headline": title,
                "description": n.get("Description"),
                "category": cat,
                "published_at": n.get("PublishTime"),
                "valid_from": n.get("StartTime"),
                "valid_to": n.get("EndTime"),
                "url": n.get("NewsURL"),
                "authority": authority,
                "kind": "news",
                "status": "closure" if severe else "notice",
                "severity": "high" if severe else "medium",
                "indicative": True,
            },
        ))
    return out


# ── live ─────────────────────────────────────────────────────────────────
def fetch_road_traffic(county: str | None) -> list[dict]:
    """Four feeds, each optional: a county may publish cameras but no news
    (Nantou does — its News endpoint answers HTTP 400), and 公路局 covers the
    provincial roads everywhere. Only when *every* feed fails is the layer
    unavailable."""
    city = _city(county)
    feats: list[dict] = []
    errors: list[str] = []
    calls: list[tuple[str, dict | None, str, str]] = []
    if city:
        calls.append((f"/v2/Road/Traffic/CCTV/City/{city}", {"$top": "5000"}, "city", "cctv"))
        calls.append((f"/v2/Road/Traffic/Live/News/City/{city}", {"$top": "100"}, "city", "news"))
    # TDX pages at 30 rows by default; the 公路局 list is nationwide, so ask for all and filter by county extent
    calls.append(("/v2/Road/Traffic/CCTV/Highway", {"$top": "20000"}, "highway", "cctv"))
    calls.append(("/v2/Road/Traffic/Live/News/Highway", {"$top": "2000"}, "highway", "news"))
    for path, params, authority, kind in calls:
        try:
            body = _get(path, params)
        except ConnectorDisabled:
            raise
        except ConnectorError as exc:
            errors.append(f"{path.split('/Traffic/')[-1]}：{exc.reason}")
            continue
        feats += map_cctv(body, county, authority) if kind == "cctv" else map_news(body, county, authority)
    if not feats and errors:
        raise ConnectorError("；".join(errors))
    return feats


SAMPLE_CCTV: dict = {
    "UpdateTime": "2026-08-22T12:00:00+08:00", "AuthorityCode": "THB", "Count": 2,
    "CCTVs": [
        {"CCTVID": "THB-14A-018", "VideoStreamURL": "https://example.invalid/stream/14a018", "VideoImageURL": "https://example.invalid/img/14a018.jpg",
         "ImageRefreshRate": 60, "PositionLon": 121.1575, "PositionLat": 24.0236, "SurveillanceDescription": "台14甲線 18K 清境",
         "RoadName": "台14甲線", "RoadSection": "霧社-清境", "LocationMile": "18K+000"},
        {"CCTVID": "THB-1-001", "VideoImageURL": "https://example.invalid/img/1.jpg", "PositionLon": 121.50, "PositionLat": 25.05,
         "SurveillanceDescription": "台1線 台北橋", "RoadName": "台1線"},
    ],
}
SAMPLE_NEWS: dict = {
    "Newses": [
        {"NewsID": "THB-20260822-01", "Title": "台14甲線 18K 清境路段坍方封閉", "NewsCategory": "2", "Description": "南投縣仁愛鄉台14甲線 18K 因豪雨坍方，雙向封閉，請改道。",
         "PublishTime": "2026-08-22T10:30:00+08:00", "StartTime": "2026-08-22T10:00:00+08:00", "EndTime": None},
        {"NewsID": "THB-20260822-02", "Title": "台9線 蘇花路廊 夜間施工", "NewsCategory": "1", "Description": "宜蘭縣蘇澳鎮夜間施工，單線通行。",
         "PublishTime": "2026-08-22T09:00:00+08:00"},
    ],
}
