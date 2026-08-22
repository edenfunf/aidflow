"""Rule-based scenario understanding — the always-available fallback.

Extracts region, hazards, mentioned impacts (as report categories) and
reporter roles from a free-text brief with keyword rules. The AI parser
(ai_agent.parse_scenario) produces the same shape; the orchestrator merges
the two so the platform can always be planned without a model.
"""
from __future__ import annotations

import re

from app.domain.categories import CATEGORIES
from app.domain.hazards import HAZARDS, detect_hazards, hazard_label
from app.utils.geo import COUNTY_CENTROIDS, TOWN_CENTROIDS, normalize_admin

_IMPACT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("road_collapse", ("坍方", "坍塌", "路基", "掏空", "落石", "崩塌")),
    ("landslide", ("土石流", "土石", "山崩", "邊坡")),
    ("flooding", ("積淹水", "淹水", "積水", "溢淹", "水淹")),
    ("road_blocked", ("道路中斷", "交通中斷", "封閉", "不通", "阻斷", "中斷")),
    ("bridge_damage", ("橋梁", "橋樑", "橋面", "斷橋", "橋")),
    ("trapped_person", ("受困", "失聯", "待救", "受傷", "孤島")),
    ("fallen_tree", ("倒木", "路樹", "樹倒")),
    ("power_outage", ("停電", "斷電")),
    ("water_outage", ("停水", "斷水")),
    ("building_damage", ("建物", "建築", "房屋", "倒塌", "龜裂", "傾斜")),
    ("fire", ("火災", "火警", "起火")),
    ("gas_leak", ("瓦斯", "氣爆")),
    ("embankment_damage", ("堤防", "護岸", "潰堤")),
    ("medical_need", ("醫療", "洗腎", "就醫", "傷患")),
]

_ROLE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("citizen", ("民眾", "居民", "住戶", "村民", "鄉親", "一般人")),
    ("village_chief", ("村里長", "里長", "村長", "鄰長")),
    ("disaster_officer", ("防災士", "防災人員")),
    ("volunteer", ("志工", "義工", "義消")),
    ("community_org", ("社區組織", "社區", "協會", "部落會議", "教會", "NGO")),
    ("agency", ("公所", "公務", "鄉公所", "縣府", "承辦")),
]

# a bare place stem followed by one of these is a street / village / feature
# name, not the township ("仁愛路" is not 仁愛鄉)
_STEM_BLOCK = "路街里村巷段橋溪山國中小學"
# …and for township stems, also an administrative suffix of another level
_TOWN_STEM_BLOCK = _STEM_BLOCK + "縣市鄉鎮區"


def detect_county(text: str) -> str | None:
    t = normalize_admin(text)
    for county in COUNTY_CENTROIDS:
        if county in t:
            return county
    # a township of a known county implies the county (南投市 → 南投縣)
    for county, towns in TOWN_CENTROIDS.items():
        if any(town in t for town in towns):
            return county
    for county in COUNTY_CENTROIDS:
        stem = county[:-1]
        if len(stem) >= 2 and re.search(stem + r"(?![" + _STEM_BLOCK + "])", t):
            return county
    return None


def detect_towns(text: str, county: str | None) -> list[str]:
    if not county:
        return []
    county = normalize_admin(county)
    t = normalize_admin(text)
    out: list[str] = []
    for town in TOWN_CENTROIDS.get(county, {}):
        if town in t:
            out.append(town)
            continue
        stem = town[:-1]
        if stem == county[:-1]:
            # "南投" alone names the county, never 南投市 — require the full name
            continue
        if len(stem) >= 2 and re.search(stem + r"(?![" + _TOWN_STEM_BLOCK + "])", t):
            out.append(town)
    return out


def detect_impacts(text: str) -> list[str]:
    t = text or ""
    found: list[str] = []
    for key, kws in _IMPACT_KEYWORDS:
        if any(kw in t for kw in kws) and key not in found:
            found.append(key)
    # "道路中斷" matched by road_blocked; a bare "橋" only counts with damage words
    if "bridge_damage" in found and not any(w in t for w in ("橋梁", "橋樑", "橋面", "斷橋", "受損", "沖毀")):
        found.remove("bridge_damage")
    return found


def detect_roles(text: str) -> list[str]:
    t = text or ""
    found = [key for key, kws in _ROLE_KEYWORDS if any(kw in t for kw in kws)]
    if "民眾" in t and "citizen" not in found:
        found.insert(0, "citizen")
    return found or ["citizen", "village_chief", "disaster_officer", "volunteer"]


def data_needs(impacts: list[str], hazards: list[str]) -> list[str]:
    needs = ["位置", "現場照片", "災情類別", "說明", "時間", "回報者角色", "處理狀態"]
    if any(h in hazards for h in ("heavy_rain", "typhoon", "flood")):
        needs += ["雨量", "河川水位", "官方特報"]
    if "landslide" in hazards or "landslide" in impacts:
        needs += ["土石流警戒"]
    if "trapped_person" in impacts:
        needs += ["受困人數"]
    needs += ["避難收容處所"]
    return list(dict.fromkeys(needs))


def suggest_name(county: str | None, towns: list[str], hazards: list[str]) -> str:
    region = (county or "") + ("".join(towns[:1]) if len(towns) == 1 else "")
    label = "".join(hazard_label(h) for h in hazards[:2]) or "災害"
    return f"{region}{label}災情通報平台" if region else f"{label}災情通報平台"


def summarize(county: str | None, towns: list[str], hazards: list[str], impacts: list[str], roles: list[str]) -> str:
    from app.domain.categories import REPORTER_ROLES

    role_labels = dict(REPORTER_ROLES)
    region = (county or "未指定地區") + ("、".join(towns) if towns else "")
    hz = "、".join(hazard_label(h) for h in hazards) or "未明確災別"
    im = "、".join(CATEGORIES[i].label for i in impacts if i in CATEGORIES) or "一般災情"
    rl = "、".join(role_labels.get(r, r) for r in roles)
    return f"地區：{region}；災害：{hz}；主要災情：{im}；回報者：{rl}。"


def parse_brief(text: str) -> dict:
    county = detect_county(text)
    towns = detect_towns(text, county)
    hazards = detect_hazards(text)
    impacts = detect_impacts(text)
    # impacts imply hazards when the brief names none
    if not hazards:
        if "landslide" in impacts or "road_collapse" in impacts:
            hazards.append("landslide")
        if "flooding" in impacts:
            hazards.append("flood")
        if "building_damage" in impacts and "fire" not in impacts:
            hazards.append("earthquake")
    hazards = [h for h in hazards if h in HAZARDS]
    roles = detect_roles(text)
    return {
        "county": county,
        "towns": towns,
        "hazards": hazards,
        "impacts": impacts,
        "reporter_roles": roles,
        "data_needs": data_needs(impacts, hazards),
        "name": suggest_name(county, towns, hazards),
        "summary": summarize(county, towns, hazards, impacts, roles),
    }
