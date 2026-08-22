"""Hazard taxonomy — what kind of disaster a platform is for.

A platform may combine several hazards (颱風 + 豪雨 + 土石流). Each hazard maps
to the report categories it makes relevant and the official/visual layers that
matter for it. The scenario profile (modules/scenarios.py) composes these.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hazard:
    key: str
    label: str
    report_categories: tuple[str, ...]
    layers: tuple[str, ...]
    keywords: tuple[str, ...]


HAZARDS: dict[str, Hazard] = {
    h.key: h
    for h in (
        Hazard(
            "typhoon", "颱風",
            ("flooding", "fallen_tree", "power_outage", "road_blocked", "road_collapse",
             "bridge_damage", "trapped_person", "building_damage", "other"),
            ("flooding", "road_damage", "shelter", "official_alert", "rainfall", "radar", "water", "reservoir",
             "debris_flow", "road_traffic", "population", "power_outage"),
            ("颱風", "台风", "typhoon", "強颱", "熱帶氣旋", "颶風"),
        ),
        Hazard(
            "heavy_rain", "豪雨",
            ("flooding", "road_collapse", "landslide", "road_blocked", "bridge_damage",
             "trapped_person", "embankment_damage", "other"),
            ("flooding", "rainfall", "radar", "water", "reservoir", "road_damage", "landslide", "debris_flow",
             "landslide_zone", "road_traffic", "official_alert", "population"),
            ("豪雨", "大雨", "暴雨", "連續降雨", "強降雨", "heavy rain", "豪大雨"),
        ),
        Hazard(
            "flood", "淹水",
            ("flooding", "embankment_damage", "trapped_person", "road_blocked",
             "power_outage", "other"),
            ("flooding", "water", "reservoir", "rainfall", "radar", "road_damage", "road_traffic", "shelter",
             "official_alert", "population"),
            ("淹水", "積水", "水災", "洪水", "積淹水", "flood", "溢堤"),
        ),
        Hazard(
            "landslide", "土石流",
            ("landslide", "road_collapse", "road_blocked", "trapped_person",
             "bridge_damage", "building_damage", "other"),
            ("landslide", "debris_flow", "landslide_zone", "road_damage", "road_traffic", "rainfall", "radar",
             "shelter", "official_alert", "population"),
            ("土石流", "坍方", "崩塌", "落石", "山崩", "邊坡", "landslide"),
        ),
        Hazard(
            "earthquake", "地震",
            ("building_damage", "trapped_person", "fire", "gas_leak", "road_collapse",
             "bridge_damage", "power_outage", "water_outage", "other"),
            ("building_damage", "trapped_people", "shelter", "fire_station",
             "official_alert", "road_damage"),
            ("地震", "餘震", "規模", "震度", "earthquake"),
        ),
        Hazard(
            "barrier_lake", "堰塞湖",
            ("flooding", "embankment_damage", "road_blocked", "trapped_person",
             "bridge_damage", "other"),
            ("flooding", "water", "rainfall", "shelter", "official_alert", "road_damage"),
            ("堰塞湖", "潰壩", "潰堤", "溢流", "barrier lake"),
        ),
    )
}

HAZARD_KEYS = tuple(HAZARDS.keys())


def detect_hazards(text: str) -> list[str]:
    """Keyword detection, order = appearance in HAZARDS (stable)."""
    low = (text or "").lower()
    found: list[str] = []
    for key, hz in HAZARDS.items():
        if any(kw.lower() in low for kw in hz.keywords):
            found.append(key)
    return found


def hazard_label(key: str) -> str:
    hz = HAZARDS.get(key)
    return hz.label if hz else key
