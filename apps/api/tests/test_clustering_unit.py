"""Deterministic clustering rules — no database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.cluster_service import (
    ClusterCandidate,
    ClusterPolicy,
    count_unique_reporters,
    pick_cluster,
    policy_from_dict,
)
from app.utils.geo import haversine_m, parse_twd97_xy, twd97_to_wgs84

T0 = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)
POLICY = ClusterPolicy(required_unique_reporters=2, radius_meters=100, time_window_minutes=60)


def _c(id, lat, lon, category="road_collapse", minutes_ago=5):
    return ClusterCandidate(id, category, lat, lon, T0 - timedelta(minutes=minutes_ago))


def test_haversine_is_sane():
    # ~111 km per degree of latitude
    assert abs(haversine_m(24.0, 121.0, 25.0, 121.0) - 111_195) < 300
    assert haversine_m(24.0, 121.0, 24.0, 121.0) == 0


def test_picks_nearest_similar_cluster_within_radius():
    near = _c("near", 24.0235, 121.1572)
    nearer = _c("nearer", 24.02352, 121.15721)
    far = _c("far", 24.0300, 121.1572)  # ~720 m north
    chosen = pick_cluster([near, far, nearer], lat=24.02353, lon=121.15722, category="road_blocked",
                          reported_at=T0, policy=POLICY)
    assert chosen is not None and chosen.id == "nearer"


def test_rejects_outside_radius_and_dissimilar_category():
    assert pick_cluster([_c("a", 24.0235, 121.1572)], lat=24.0250, lon=121.1572, category="road_collapse",
                        reported_at=T0, policy=POLICY) is None  # ~167 m
    assert pick_cluster([_c("a", 24.0235, 121.1572, category="flooding")], lat=24.0235, lon=121.1572,
                        category="road_collapse", reported_at=T0, policy=POLICY) is None


def test_rejects_outside_time_window():
    stale = _c("stale", 24.0235, 121.1572, minutes_ago=61)
    assert pick_cluster([stale], lat=24.0235, lon=121.1572, category="road_collapse",
                        reported_at=T0, policy=POLICY) is None
    fresh = _c("fresh", 24.0235, 121.1572, minutes_ago=59)
    assert pick_cluster([fresh], lat=24.0235, lon=121.1572, category="road_collapse",
                        reported_at=T0, policy=POLICY).id == "fresh"


def test_unique_reporter_counting():
    assert count_unique_reporters(["a", "a", "a"], count_anonymous=True) == 1
    assert count_unique_reporters(["a", "b"], count_anonymous=True) == 2
    assert count_unique_reporters(["a", None, None], count_anonymous=True) == 3
    assert count_unique_reporters(["a", None, None], count_anonymous=False) == 1
    assert count_unique_reporters([], count_anonymous=True) == 0


def test_policy_merges_and_clamps():
    p = policy_from_dict({"required_unique_reporters": 3, "radius_meters": 150})
    assert (p.required_unique_reporters, p.radius_meters, p.time_window_minutes) == (3, 150, 60)
    p = policy_from_dict({"required_unique_reporters": 0, "radius_meters": 999999, "time_window_minutes": -5})
    assert (p.required_unique_reporters, p.radius_meters, p.time_window_minutes) == (1, 5000, 1)
    p = policy_from_dict({"radius_meters": "not-a-number"})
    assert p.radius_meters == 100
    assert policy_from_dict(None).required_unique_reporters == 2


def test_twd97_conversion_matches_known_point():
    # TM2 origin: x=250000 on the 121°E meridian; y≈2655000 is ~24.0°N
    lat, lon = twd97_to_wgs84(250000.0, 2655000.0)
    assert abs(lon - 121.0) < 1e-4
    assert abs(lat - 24.0) < 0.02
    # WRA sample: 新磺溪橋 (新北市金山區) should land in northern Taiwan
    point = parse_twd97_xy("313411.44 2790930.63")
    assert point is not None
    assert 25.2 < point[0] < 25.3 and 121.6 < point[1] < 121.7
    assert parse_twd97_xy("garbage") is None
    assert parse_twd97_xy("") is None
