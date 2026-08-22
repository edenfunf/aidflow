"""Report category taxonomy.

A *report category* is what a citizen picks on the form ("發生什麼事？"). The
full taxonomy lives here; a platform only exposes the subset its scenario
profile selects. ``SIMILAR_GROUPS`` defines which categories count as "相近災情"
for the clustering engine (e.g. a 道路坍方 and a 道路中斷 report at the same
spot are the same incident).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportCategory:
    key: str
    label: str
    # default severity hint when the citizen does not say otherwise
    default_severity: str
    # map layer this category feeds (see modules/layers)
    layer: str
    # life-safety categories are escalated by triage regardless of severity
    life_safety: bool = False


CATEGORIES: dict[str, ReportCategory] = {
    c.key: c
    for c in (
        ReportCategory("road_collapse", "道路坍方", "high", "road_damage"),
        ReportCategory("road_blocked", "道路中斷", "high", "road_damage"),
        ReportCategory("flooding", "積淹水", "medium", "flooding"),
        ReportCategory("landslide", "土石流", "high", "landslide"),
        ReportCategory("trapped_person", "人員受困", "critical", "trapped_people", True),
        ReportCategory("bridge_damage", "橋梁受損", "high", "road_damage"),
        ReportCategory("fallen_tree", "倒木", "low", "road_damage"),
        ReportCategory("power_outage", "停電", "medium", "lifeline"),
        ReportCategory("water_outage", "停水", "low", "lifeline"),
        ReportCategory("building_damage", "建築損害", "high", "building_damage"),
        ReportCategory("fire", "火災", "critical", "building_damage", True),
        ReportCategory("gas_leak", "瓦斯外洩", "critical", "building_damage", True),
        ReportCategory("embankment_damage", "堤防受損", "high", "flooding"),
        ReportCategory("medical_need", "醫療需求", "high", "trapped_people", True),
        ReportCategory("other", "其他", "medium", "other"),
    )
}

# categories that cluster together as "the same incident"
SIMILAR_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"road_collapse", "road_blocked", "landslide", "fallen_tree"}),
    frozenset({"flooding", "embankment_damage"}),
    frozenset({"bridge_damage", "road_blocked"}),
    frozenset({"building_damage", "fire", "gas_leak"}),
    frozenset({"trapped_person", "medical_need"}),
    frozenset({"power_outage", "water_outage"}),
)


def are_similar(a: str, b: str) -> bool:
    """Same category, or both in one similarity group."""
    if a == b:
        return True
    return any(a in g and b in g for g in SIMILAR_GROUPS)


def category_label(key: str) -> str:
    c = CATEGORIES.get(key)
    return c.label if c else key


def layer_for(key: str) -> str:
    c = CATEGORIES.get(key)
    return c.layer if c else "other"


# ── reporter roles ────────────────────────────────────────────────────────
REPORTER_ROLES: tuple[tuple[str, str], ...] = (
    ("citizen", "一般民眾"),
    ("village_chief", "村里長"),
    ("disaster_officer", "防災士"),
    ("volunteer", "志工"),
    ("community_org", "社區組織"),
    ("agency", "公務單位"),
)
REPORTER_ROLE_KEYS = frozenset(k for k, _ in REPORTER_ROLES)

# roles whose reports carry more weight in triage (trained / accountable)
TRUSTED_ROLES = frozenset({"village_chief", "disaster_officer", "agency"})

SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")
_SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def severity_rank(value: str) -> int:
    return _SEVERITY_RANK.get(value, 1)


def max_severity(values: list[str]) -> str:
    best = "low"
    for v in values:
        if _SEVERITY_RANK.get(v, 0) > _SEVERITY_RANK[best]:
            best = v
    return best


def escalate(severity: str, category: str, reporter_role: str | None) -> str:
    """Deterministic severity triage for a single report."""
    cat = CATEGORIES.get(category)
    rank = _SEVERITY_RANK.get(severity, 1)
    if cat and cat.life_safety:
        rank = max(rank, _SEVERITY_RANK["high"])
    if reporter_role in TRUSTED_ROLES and rank < _SEVERITY_RANK["high"]:
        # a trained reporter's call is trusted one notch up, never to critical
        rank = rank + 1
    return SEVERITIES[rank]
