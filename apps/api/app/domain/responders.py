"""Responder rules — which kind of unit handles which report category, and
what vehicles such a unit sends. Deterministic; no model involved.

Unit kinds:
  fire          消防（大隊／分隊）        → 消防車 / 救護車
  police        警察（分局／派出所）      → 警車
  town_office   鄉鎮市公所               → 工程車
  highway       公路局 工務段            → 工程車
  river         水利署 河川分署          → 工程車
  slope         農業部 農村發展及水土保持署 → 工程車
  power         台電 區營業處            → 工程車
  water_supply  台水 營運所              → 工程車
"""
from __future__ import annotations

from dataclasses import dataclass

UNIT_KIND_LABELS: dict[str, str] = {
    "fire": "消防單位",
    "police": "警察單位",
    "town_office": "鄉鎮公所",
    "highway": "公路局工務段",
    "river": "水利署河川分署",
    "slope": "水保署分署",
    "power": "台電",
    "water_supply": "自來水公司",
}

VEHICLE_KIND_LABELS: dict[str, str] = {
    "fire_engine": "消防車",
    "ambulance": "救護車",
    "police_car": "警車",
    "works_truck": "工程車",
}

# category -> unit kinds, primary first
CATEGORY_RESPONDERS: dict[str, tuple[str, ...]] = {
    "trapped_person": ("fire", "police", "town_office"),
    "medical_need": ("fire", "town_office"),
    "fire": ("fire", "police"),
    "gas_leak": ("fire", "police"),
    "building_damage": ("fire", "town_office"),
    "road_collapse": ("highway", "town_office", "police"),
    "road_blocked": ("highway", "town_office", "police"),
    "bridge_damage": ("highway", "town_office"),
    "fallen_tree": ("town_office", "highway", "power"),
    "landslide": ("slope", "town_office", "fire"),
    "flooding": ("river", "town_office", "fire"),
    "embankment_damage": ("river", "town_office"),
    "power_outage": ("power", "town_office"),
    "water_outage": ("water_supply", "town_office"),
    "other": ("town_office", "police"),
}


def responder_kinds(category: str) -> tuple[str, ...]:
    return CATEGORY_RESPONDERS.get(category, CATEGORY_RESPONDERS["other"])


def vehicles_for(unit_kind: str, category: str) -> list[str]:
    """Vehicles a unit of this kind sends for this category (a realistic
    first-response package, not the whole station)."""
    if unit_kind == "fire":
        if category in ("trapped_person", "building_damage"):
            return ["fire_engine", "fire_engine", "ambulance"]
        if category == "medical_need":
            return ["ambulance", "fire_engine"]
        if category in ("fire", "gas_leak"):
            return ["fire_engine", "fire_engine"]
        return ["fire_engine", "ambulance"]
    if unit_kind == "police":
        if category in ("trapped_person", "road_collapse", "road_blocked", "fire"):
            return ["police_car", "police_car"]
        return ["police_car"]
    if category in ("road_collapse", "road_blocked", "bridge_damage", "landslide", "embankment_damage", "flooding"):
        return ["works_truck", "works_truck"]
    return ["works_truck"]


@dataclass(frozen=True)
class AgencySpec:
    """A configured (non-open-data) responder. Locations are the township
    centre unless ``lat``/``lon`` are given — flagged ``indicative`` so the UI
    never presents them as surveyed positions."""

    name: str
    kind: str
    county: str
    town: str | None
    lat: float | None = None
    lon: float | None = None
    phone: str | None = None


# Agencies that actually exist for the Nantou demo region. Positions are
# indicative (township centre) unless a verified coordinate is known.
NANTOU_AGENCIES: tuple[AgencySpec, ...] = (
    AgencySpec("南投縣政府工務處道路養護科", "highway", "南投縣", "南投市"),
    AgencySpec("公路局中區養護工程分局埔里工務段", "highway", "南投縣", "埔里鎮"),
    AgencySpec("公路局中區養護工程分局信義工務段", "highway", "南投縣", "信義鄉"),
    AgencySpec("經濟部水利署第四河川分署", "river", "南投縣", "南投市"),
    AgencySpec("農業部農村發展及水土保持署南投分署", "slope", "南投縣", "南投市"),
    AgencySpec("台電南投區營業處", "power", "南投縣", "南投市"),
    AgencySpec("台灣自來水公司第四區管理處", "water_supply", "南投縣", "南投市"),
    AgencySpec("南投縣政府警察局埔里分局", "police", "南投縣", "埔里鎮"),
    AgencySpec("南投縣政府警察局仁愛分局", "police", "南投縣", "仁愛鄉"),
    AgencySpec("南投縣政府警察局信義分局", "police", "南投縣", "信義鄉"),
    AgencySpec("南投縣政府警察局集集分局", "police", "南投縣", "集集鎮"),
    AgencySpec("仁愛鄉公所", "town_office", "南投縣", "仁愛鄉"),
    AgencySpec("信義鄉公所", "town_office", "南投縣", "信義鄉"),
    AgencySpec("埔里鎮公所", "town_office", "南投縣", "埔里鎮"),
    AgencySpec("國姓鄉公所", "town_office", "南投縣", "國姓鄉"),
    AgencySpec("水里鄉公所", "town_office", "南投縣", "水里鄉"),
    AgencySpec("魚池鄉公所", "town_office", "南投縣", "魚池鄉"),
    AgencySpec("集集鎮公所", "town_office", "南投縣", "集集鎮"),
    AgencySpec("中寮鄉公所", "town_office", "南投縣", "中寮鄉"),
    AgencySpec("草屯鎮公所", "town_office", "南投縣", "草屯鎮"),
    AgencySpec("竹山鎮公所", "town_office", "南投縣", "竹山鎮"),
    AgencySpec("鹿谷鄉公所", "town_office", "南投縣", "鹿谷鄉"),
    AgencySpec("名間鄉公所", "town_office", "南投縣", "名間鄉"),
    AgencySpec("南投市公所", "town_office", "南投縣", "南投市"),
)

AGENCIES_BY_COUNTY: dict[str, tuple[AgencySpec, ...]] = {"南投縣": NANTOU_AGENCIES}
