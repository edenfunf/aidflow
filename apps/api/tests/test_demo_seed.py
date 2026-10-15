"""The demo scenario must run through the real pipeline and be internally
consistent (needs a live database)."""
from __future__ import annotations


def test_demo_seed_is_consistent_and_idempotent(client, monkeypatch):
    # keep the test's demo platform apart from a developer's live demo (tests
    # share the dev database)
    from app.services import demo_seed_service

    monkeypatch.setattr(demo_seed_service, "DEMO_KEY", "nantou-2026-heavy-rain-test")
    monkeypatch.setattr(demo_seed_service, "DEMO_SLUG", "nantou-heavy-rain-demo-test")
    first = client.post("/v1/demo/nantou", params={"force": "true"}).json()
    assert first["seeded"] is True and first["cases"] >= 10
    slug = first["slug"]

    again = client.post("/v1/demo/nantou").json()
    assert again.get("skipped") is True

    s = client.get(f"/v1/public/platforms/{slug}/situation").json()
    assert s["cases_total"] == s["cases_pending"] + s["cases_active"] + s["cases_community"] + s["cases_done"]
    assert s["cases_pending"] >= 3 and s["cases_active"] >= 3 and s["cases_community"] >= 2 and s["cases_done"] >= 3
    assert s["cases_community_submitted"] >= 1
    towns = {t["key"] for t in s["by_town"]}
    assert {"仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"} <= towns
    cats = {c["key"] for c in s["by_category"]}
    assert {"road_collapse", "landslide", "flooding", "bridge_damage", "trapped_person"} <= cats

    cases = client.get(f"/v1/public/platforms/{slug}/cases", params={"limit": 100}).json()["items"]
    statuses = {c["status"] for c in cases}
    assert {"pending_review", "reported_emic", "emic_processing", "community_open", "community_submitted", "closed"} <= statuses
    assert {c["track"] for c in cases if c["status"] == "closed"} == {"emic", "community"}
    # the duplicate-sender site (霧社) must NOT have become a case
    assert not any(c["town"] == "仁愛鄉" and c["category"] == "flooding" for c in cases)
    # an EMIC case has a full, chronological public timeline with EMIC status
    emic_case = next(c for c in cases if c["status"] == "emic_processing" and c["emic_status"])
    detail = client.get(f"/v1/public/platforms/{slug}/cases/{emic_case['id']}").json()
    labels = [t["label"] for t in detail["timeline"]]
    assert "已上報 EMIC" in labels and "處理中" in labels
    ats = [t["at"] for t in detail["timeline"]]
    assert ats == sorted(ats)
    # closed cases are off the public map; open clusters below threshold are in the console
    feats = client.get(f"/v1/public/platforms/{slug}/map").json()["features"]
    closed_ids = {c["id"] for c in cases if c["status"] == "closed"}
    assert not any(f["properties"].get("case_id") in closed_ids for f in feats)
    clusters = client.get(f"/v1/platforms/{first['platform_id']}/clusters", params={"status": "open"}).json()
    assert clusters["total"] >= 3
    text = client.get(f"/v1/public/platforms/{slug}/map").text
    assert "0912000101" not in text and "王村長" not in text and "EMIC-1150903" not in text


def test_demo_can_be_loaded_into_a_fresh_platform(client, platform):
    """The console's one-click demo: same story, this platform, real pipeline."""
    first = client.post(f"/v1/platforms/{platform['id']}/demo").json()
    assert first["seeded"] is True and first["cases"] >= 8 and first["platform_id"] == platform["id"]
    s = client.get(f"/v1/public/platforms/{platform['slug']}/situation").json()
    assert s["cases_total"] == first["cases"] and s["cases_pending"] >= 1
    # loading again with replace starts over
    again = client.post(f"/v1/platforms/{platform['id']}/demo", params={"replace": "true"}).json()
    assert again["cases"] == first["cases"]
    s2 = client.get(f"/v1/public/platforms/{platform['slug']}/situation").json()
    assert s2["cases_total"] == first["cases"]
    detail = client.get(f"/v1/platforms/{platform['id']}").json()
    assert detail["configuration"].get("demo") is True


def test_demo_can_be_translated_to_another_county(client):
    """The console seeds the same story into a platform anywhere: coordinates
    shift to that county, and the one report that carries no location must not
    break the transform."""
    created = client.post("/v1/platforms", json={"name": "測試-跨縣示範", "hazards": ["earthquake", "landslide"],
                                                  "county": "花蓮縣", "towns": ["秀林鄉"]}).json()
    r = client.post(f"/v1/platforms/{created['id']}/demo").json()
    assert r["seeded"] is True and r["translated"] is True and r["cases"] >= 8

    s = client.get(f"/v1/public/platforms/{created['slug']}/situation").json()
    assert s["cases_total"] == r["cases"]
    m = client.get(f"/v1/public/platforms/{created['slug']}/map").json()
    pts = [f["geometry"]["coordinates"] for f in m["features"] if f["geometry"]["type"] == "Point"]
    assert pts, "seeded platform should have mapped features"
    # every seeded point sits in Hualien, not Nantou
    assert all(lon > 121.2 for lon, _lat in pts), pts[:3]

    from app.utils.geo import COUNTY_CENTROIDS, haversine_m

    clat, clon = COUNTY_CENTROIDS["花蓮縣"]
    worst = max(haversine_m(clat, clon, lat, lon) for lon, lat in pts)
    assert worst <= 20_000, f"seeded point {worst / 1000:.1f} km from 花蓮 centre"

    reports = client.get(f"/v1/public/platforms/{created['slug']}/reports").json()
    items = reports.get("items", reports)
    labels = [str(r.get("location_label") or "") for r in items]
    assert any(labels), "public reports should carry a coarse location label"
    joined = " ".join(labels)
    for ghost in ("仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"):
        assert ghost not in joined, f"{ghost} does not exist in 花蓮縣: {joined[:200]}"
