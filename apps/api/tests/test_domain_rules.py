"""Pure domain rules — no database."""
from __future__ import annotations

import pytest

from app.domain.case_states import (
    CaseStatus,
    InvalidTransitionError,
    assert_transition,
    can_transition,
    next_statuses,
    phase_of,
)
from app.domain.categories import CATEGORIES, are_similar, escalate, max_severity
from app.domain.hazards import detect_hazards
from app.modules import registry
from app.modules.scenarios import compose_profile


# ── state machine ─────────────────────────────────────────────────────────
def test_happy_path_transitions_are_allowed():
    path = ["awaiting_dispatch", "assigned", "en_route", "on_site", "processing", "resolved", "closed"]
    for frm, to in zip(path, path[1:]):
        assert can_transition(frm, to), f"{frm} -> {to}"


@pytest.mark.parametrize("frm,to", [
    ("awaiting_dispatch", "resolved"),  # cannot skip dispatch
    ("closed", "processing"),  # terminal
    ("dismissed", "awaiting_dispatch"),  # terminal
    ("assigned", "resolved"),  # must reach site first
    ("resolved", "assigned"),
    ("bogus", "assigned"),
    ("assigned", "bogus"),
])
def test_illegal_transitions_are_rejected(frm, to):
    assert not can_transition(frm, to)
    with pytest.raises(InvalidTransitionError):
        assert_transition(frm, to)


def test_reopen_and_cancel_dispatch_paths():
    assert can_transition("resolved", "processing")  # reopen
    assert can_transition("assigned", "awaiting_dispatch")  # cancel dispatch
    assert "closed" not in next_statuses("processing")
    assert next_statuses("closed") == []


def test_phase_mapping_covers_every_status():
    for s in CaseStatus:
        assert phase_of(s) in {"pending", "active", "done", "dismissed"}


# ── categories / triage ───────────────────────────────────────────────────
def test_similar_categories_cluster_together():
    assert are_similar("road_collapse", "road_blocked")
    assert are_similar("landslide", "road_collapse")
    assert are_similar("flooding", "flooding")
    assert not are_similar("flooding", "road_collapse")
    assert not are_similar("trapped_person", "power_outage")


def test_life_safety_is_escalated_and_trusted_roles_bump_one_notch():
    assert escalate("low", "trapped_person", "citizen") == "high"
    assert escalate("critical", "trapped_person", "citizen") == "critical"
    assert escalate("medium", "flooding", "citizen") == "medium"
    assert escalate("medium", "flooding", "village_chief") == "high"
    # a trusted role never manufactures "critical" on its own
    assert escalate("high", "flooding", "disaster_officer") == "high"
    assert max_severity(["low", "critical", "medium"]) == "critical"


def test_hazard_detection_handles_combined_briefs():
    found = detect_hazards("南投縣仁愛鄉因颱風帶來連續豪雨，多處山區道路可能發生坍方、土石流與積淹水")
    assert {"typhoon", "heavy_rain", "landslide", "flood"} <= set(found)
    assert detect_hazards("花蓮外海發生規模 7.2 地震") == ["earthquake"]
    assert detect_hazards("某種不明狀況") == []


# ── registry / scenario composition ───────────────────────────────────────
def test_registry_has_required_aidflow_modules():
    required = {
        "report_form", "geo_location", "photo_upload", "report_category", "reporter_role",
        "duplicate_report_merge", "geo_cluster", "two_report_trigger", "incident_case_creation",
        "severity_triage", "case_dispatch", "case_assignment", "case_status",
        "incident_map", "report_cluster_layer", "heatmap_layer", "official_alert_layer",
        "rainfall_layer", "water_layer", "shelter_layer",
        "public_timeline", "status_progress", "incident_statistics", "trend_visualization",
        "privacy_mask", "personal_data_redaction", "line_notify",
    }
    ids = {m.id for m in registry.all()}
    missing = required - ids
    assert not missing, missing
    for layer in registry.layers():
        assert layer.layer_key


def test_compose_profile_for_heavy_rain_landslide_in_nantou():
    profile = compose_profile(["typhoon", "heavy_rain", "landslide", "flood"], "南投縣", ["仁愛鄉"],
                              mentioned_categories=["road_collapse", "landslide", "flooding"])
    cats = [c["key"] for c in profile.report_categories]
    assert cats[:3] == ["road_collapse", "landslide", "flooding"]
    assert cats[-1] == "other"
    assert "gas_leak" not in cats  # not a rain hazard category
    assert {"rainfall", "water", "landslide", "flooding", "shelter", "fire_station"} <= set(profile.layers)
    assert set(registry.core_ids()) <= set(profile.modules)
    assert "nantou_open_data_connector" in profile.modules


def test_compose_profile_for_earthquake_elsewhere_skips_nantou_connector():
    profile = compose_profile(["earthquake"], "花蓮縣", [])
    cats = {c["key"] for c in profile.report_categories}
    assert {"building_damage", "trapped_person", "gas_leak"} <= cats
    assert "landslide" not in profile.layers or "landslide" in CATEGORIES
    assert "fire_station" not in profile.layers
    assert "nantou_open_data_connector" not in profile.modules
    assert "water" not in profile.layers
