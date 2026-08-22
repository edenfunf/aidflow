"""NCDR 民生示警公開資料平台 (CAP v1.2) connector.

The platform publishes multi-hazard alerts (淹水、土石流、道路封閉、停水…) in
CAP. Feed access requires a platform membership, so the live URL is supplied
through ``NCDR_CAP_FEED_URL``; without it the layer is reported as disabled.
The CAP mapper accepts JSON (one alert or a list) or CAP XML and is tested
offline.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from app.connectors.base import (
    ConnectorDisabled,
    ConnectorError,
    feature,
    http_get,
    matches_county,
    polygon_feature,
)
from app.core.config import settings
from app.utils.geo import COUNTY_CENTROIDS, normalize_admin

SOURCE = "ncdr"
HOMEPAGE = "https://alerts.ncdr.nat.gov.tw/"
ATTRIBUTION = "國家災害防救科技中心 民生示警公開資料平台（CAP）"

_CAP_SEVERITY = {"extreme": "critical", "severe": "high", "moderate": "medium", "minor": "low"}
_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def is_live_enabled() -> bool:
    return bool(settings.NCDR_CAP_FEED_URL)


def cap_severity(value: str | None) -> str:
    return _CAP_SEVERITY.get((value or "").strip().lower(), "medium")


def cap_polygon_to_rings(polygon: str | None) -> list | None:
    """CAP <polygon> is 'lat,lon lat,lon ...'; GeoJSON wants [[lon, lat], ...]."""
    if not polygon or not polygon.strip():
        return None
    coords = []
    for pair in polygon.strip().split():
        try:
            lat_s, lon_s = pair.split(",")
            coords.append([float(lon_s), float(lat_s)])
        except ValueError:
            return None
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return [coords]


def _county_of(area_desc: str | None) -> str | None:
    text = normalize_admin(area_desc)
    for county in COUNTY_CENTROIDS:
        if county in text:
            return county
    return None


def _info_to_feature(identifier: str, idx: int, info: dict, sent: str | None, county: str | None) -> dict | None:
    areas = info.get("area") or []
    if isinstance(areas, dict):
        areas = [areas]
    area = areas[0] if areas else {}
    desc = area.get("areaDesc")
    if county and not matches_county(desc, county):
        return None
    props = {
        "name": info.get("event") or info.get("headline") or "示警",
        "headline": info.get("headline") or info.get("event"),
        "description": info.get("description"),
        "instruction": info.get("instruction"),
        "area": desc,
        "severity": cap_severity(info.get("severity")),
        "urgency": info.get("urgency"),
        "certainty": info.get("certainty"),
        "issuer": info.get("senderName") or "NCDR",
        "sent": sent,
        "valid_to": info.get("expires"),
        "status": "active",
        "kind": "cap",
    }
    rings = cap_polygon_to_rings(area.get("polygon"))
    fid = f"{SOURCE}:{identifier}#{idx}"
    if rings:
        return polygon_feature(id=fid, source=SOURCE, layer="official_alert", rings=rings, properties=props)
    centre = COUNTY_CENTROIDS.get(_county_of(desc) or "")
    if centre is None:
        return None
    return feature(id=fid, source=SOURCE, layer="official_alert", lat=centre[0], lon=centre[1], properties=props)


def map_cap(payload: dict | list, county: str | None = None) -> list[dict]:
    alerts = payload if isinstance(payload, list) else [payload]
    out: list[dict] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        identifier = alert.get("identifier") or alert.get("id") or "ncdr"
        infos = alert.get("info") or []
        if isinstance(infos, dict):
            infos = [infos]
        for idx, info in enumerate(infos):
            f = _info_to_feature(str(identifier), idx, info, alert.get("sent"), county)
            if f:
                out.append(f)
    return out


def parse_cap_xml(text: str) -> list[dict]:
    """Minimal CAP 1.2 XML → the same dict shape map_cap consumes."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ConnectorError("CAP XML 解析失敗") from exc
    alerts = [root] if root.tag.endswith("alert") else root.findall(".//cap:alert", _NS)
    out: list[dict] = []
    for a in alerts:
        def t(el, name):
            node = el.find(f"cap:{name}", _NS)
            return node.text if node is not None else None

        infos = []
        for info in a.findall("cap:info", _NS):
            areas = [{"areaDesc": t(ar, "areaDesc"), "polygon": t(ar, "polygon")} for ar in info.findall("cap:area", _NS)]
            infos.append({
                "event": t(info, "event"), "headline": t(info, "headline"), "description": t(info, "description"),
                "instruction": t(info, "instruction"), "severity": t(info, "severity"), "urgency": t(info, "urgency"),
                "certainty": t(info, "certainty"), "expires": t(info, "expires"), "senderName": t(info, "senderName"),
                "area": areas,
            })
        out.append({"identifier": t(a, "identifier"), "sent": t(a, "sent"), "info": infos})
    return out


def fetch_cap(county: str | None) -> list[dict]:
    if not is_live_enabled():
        raise ConnectorDisabled("未設定 NCDR_CAP_FEED_URL（需民生示警平台會員授權）")
    resp = http_get(settings.NCDR_CAP_FEED_URL)
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        return map_cap(resp.json(), county)
    return map_cap(parse_cap_xml(resp.text), county)


SAMPLE_CAP: dict = {
    "identifier": "WRA_FloodWarn_20260821105730_0001",
    "sender": "ncdr.nat.gov.tw",
    "sent": "2026-08-21T10:57:30+08:00",
    "status": "Actual",
    "msgType": "Alert",
    "info": [
        {"event": "淹水警戒", "severity": "Severe", "certainty": "Observed", "urgency": "Immediate",
         "headline": "南投縣埔里鎮發布一級淹水警戒", "description": "未來 3 小時內可能積淹水。",
         "senderName": "經濟部水利署",
         "area": [{"areaDesc": "南投縣埔里鎮",
                   "polygon": "23.94,120.94 23.94,120.99 23.99,120.99 23.99,120.94 23.94,120.94"}]},
        {"event": "土石流黃色警戒", "severity": "Moderate", "certainty": "Likely",
         "headline": "南投縣仁愛鄉土石流黃色警戒", "senderName": "農業部農村發展及水土保持署",
         "area": [{"areaDesc": "南投縣仁愛鄉"}]},
        {"event": "大雨特報", "severity": "Moderate", "headline": "花蓮縣大雨特報",
         "area": [{"areaDesc": "花蓮縣"}]},
    ],
}
