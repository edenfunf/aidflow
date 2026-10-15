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
    track_of,
)
from app.domain.permissions import Perm, has_perm
from app.domain.categories import CATEGORIES, are_similar, escalate, max_severity
from app.domain.hazards import detect_hazards
from app.modules import registry
from app.modules.scenarios import compose_profile


# ── state machine ─────────────────────────────────────────────────────────
def test_both_tracks_are_allowed_paths():
    for path in (["pending_review", "reported_emic", "emic_processing", "closed"],
                 ["pending_review", "community_open", "community_submitted", "closed"],
                 ["pending_review", "dismissed"]):
        for frm, to in zip(path, path[1:]):
            assert can_transition(frm, to), f"{frm} -> {to}"


@pytest.mark.parametrize("frm,to", [
    ("pending_review", "closed"),  # nothing closes without a review decision
    ("pending_review", "emic_processing"),  # must be reported first
    ("pending_review", "community_submitted"),
    ("closed", "reported_emic"),  # terminal
    ("dismissed", "pending_review"),  # terminal
    ("emic_processing", "community_open"),  # an EMIC case never goes back to citizens
    ("community_submitted", "dismissed"),
    ("bogus", "closed"),
    ("pending_review", "bogus"),
])
def test_illegal_transitions_are_rejected(frm, to):
    assert not can_transition(frm, to)
    with pytest.raises(InvalidTransitionError):
        assert_transition(frm, to)


def test_community_reject_and_escalation_paths():
    assert can_transition("community_submitted", "community_open")  # 退回
    assert can_transition("community_open", "reported_emic")  # 改列上報
    assert can_transition("community_submitted", "reported_emic")
    assert next_statuses("pending_review") == ["reported_emic", "community_open", "dismissed"]
    assert next_statuses("closed") == [] and next_statuses("dismissed") == []


def test_phase_and_track_mapping_covers_every_status():
    for s in CaseStatus:
        assert phase_of(s) in {"pending", "active", "community", "done", "dismissed"}
    assert track_of("reported_emic") == "emic" and track_of("community_submitted") == "community"
    assert track_of("pending_review") is None


# ── roles ─────────────────────────────────────────────────────────────────
def test_permission_matrix_matches_the_design_document():
    assert has_perm("officer", Perm.review_cases) and has_perm("officer", Perm.view_pii)
    assert not has_perm("officer", Perm.manage_platforms) and not has_perm("officer", Perm.view_audit)
    assert has_perm("supervisor", Perm.view_pii) and has_perm("supervisor", Perm.view_audit)
    assert not has_perm("supervisor", Perm.review_cases)
    assert has_perm("admin", Perm.manage_users) and has_perm("admin", Perm.manage_line)
    assert not has_perm("admin", Perm.view_pii) and not has_perm("admin", Perm.review_cases)
    assert all(has_perm(r, Perm.view_console) for r in ("officer", "supervisor", "admin"))
    assert not has_perm(None, Perm.view_console) and not has_perm("citizen", Perm.view_console)


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
        "severity_triage", "case_review", "case_status", "emic_report", "community_handling",
        "incident_map", "report_cluster_layer", "heatmap_layer", "official_alert_layer",
        "rainfall_layer", "water_layer", "shelter_layer",
        "public_timeline", "status_progress", "incident_statistics", "trend_visualization",
        "privacy_mask", "personal_data_redaction", "line_group_notify", "progress_subscription", "map_embed",
    }
    ids = {m.id for m in registry.all()}
    missing = required - ids
    assert not missing, missing
    assert not {"case_dispatch", "case_assignment", "line_notify"} & ids  # retired
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
