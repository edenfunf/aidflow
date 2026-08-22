"""The demo scenario must run through the real pipeline and be internally
consistent (needs a live database)."""
from __future__ import annotations


def test_demo_seed_is_consistent_and_idempotent(client, monkeypatch):
    # keep the test's demo platform apart from a developer's live demo (tests
    # share the dev database and run with OSRM stubbed)
    from app.services import demo_seed_service

    monkeypatch.setattr(demo_seed_service, "DEMO_KEY", "nantou-2026-heavy-rain-test")
    monkeypatch.setattr(demo_seed_service, "DEMO_SLUG", "nantou-heavy-rain-demo-test")
    first = client.post("/v1/demo/nantou", params={"force": "true"}).json()
    assert first["seeded"] is True and first["cases"] >= 8
    slug = first["slug"]

    again = client.post("/v1/demo/nantou").json()
    assert again.get("skipped") is True

    s = client.get(f"/v1/public/platforms/{slug}/situation").json()
    assert s["cases_total"] == s["cases_pending"] + s["cases_active"] + s["cases_done"]
    assert s["cases_pending"] >= 2 and s["cases_active"] >= 3 and s["cases_done"] >= 3
    towns = {t["key"] for t in s["by_town"]}
    assert {"仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"} <= towns
    cats = {c["key"] for c in s["by_category"]}
    assert {"road_collapse", "landslide", "flooding", "bridge_damage", "trapped_person"} <= cats

    cases = client.get(f"/v1/public/platforms/{slug}/cases", params={"limit": 100}).json()["items"]
    statuses = {c["status"] for c in cases}
    assert {"awaiting_dispatch", "assigned", "en_route", "on_site", "processing", "resolved", "closed"} <= statuses
    # the duplicate-sender site (霧社) must NOT have become a case
    assert not any(c["town"] == "仁愛鄉" and c["category"] == "flooding" for c in cases)
    # a resolved case has a full, chronological public timeline
    resolved = next(c for c in cases if c["status"] == "resolved")
    detail = client.get(f"/v1/public/platforms/{slug}/cases/{resolved['id']}").json()
    labels = [t["label"] for t in detail["timeline"]]
    assert "已派員" in labels and "已完成" in labels
    ats = [t["at"] for t in detail["timeline"]]
    assert ats == sorted(ats)
    # clusters below threshold are visible to the console as open clusters
    clusters = client.get(f"/v1/platforms/{first['platform_id']}/clusters", params={"status": "open"}).json()
    assert clusters["total"] >= 3
    text = client.get(f"/v1/public/platforms/{slug}/map").text
    assert "0912000101" not in text and "王村長" not in text


def test_demo_can_be_loaded_into_a_fresh_platform(client, platform):
    """The console's one-click demo: same story, this platform, real pipeline."""
    first = client.post(f"/v1/platforms/{platform['id']}/demo").json()
    assert first["seeded"] is True and first["cases"] >= 8 and first["platform_id"] == platform["id"]
    s = client.get(f"/v1/public/platforms/{platform['slug']}/situation").json()
    assert s["cases_total"] == first["cases"] and s["cases_pending"] >= 1
    # loading again without replace stacks; with replace it starts over
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
    plan = client.post("/v1/agent/plan", json={"message": "花蓮縣秀林鄉地震後山區道路坍方，部落聯外中斷。"}).json()
    draft = plan["draft"]
    draft["name"] = "測試-跨縣示範"
    created = client.post("/v1/agent/execute", json=draft).json()["platform"]
    r = client.post(f"/v1/platforms/{created['id']}/demo").json()
    assert r["seeded"] is True and r["translated"] is True and r["cases"] >= 8

    s = client.get(f"/v1/public/platforms/{created['slug']}/situation").json()
    assert s["cases_total"] == r["cases"]
    m = client.get(f"/v1/public/platforms/{created['slug']}/map").json()
    pts = [f["geometry"]["coordinates"] for f in m["features"] if f["geometry"]["type"] == "Point"]
    assert pts, "seeded platform should have mapped features"
    # every seeded point sits in Hualien, not Nantou
    assert all(lon > 121.2 for lon, _lat in pts), pts[:3]

    # ...and on land. 南投 is a wide inland county; carrying its full spread
    # across to a narrow coastal county used to drop half the incidents into
    # the Pacific, so the scene is shrunk about the target county's centre.
    from app.utils.geo import COUNTY_CENTROIDS, haversine_m

    clat, clon = COUNTY_CENTROIDS["花蓮縣"]
    worst = max(haversine_m(clat, clon, lat, lon) for lon, lat in pts)
    assert worst <= 20_000, f"seeded point {worst / 1000:.1f} km from 花蓮 centre"

    # A township that does not exist in the target county must never be
    # invented. The public feed masks `address`, so assert on the coarse
    # `location_label` it actually publishes — that is what a citizen reads.
    reports = client.get(f"/v1/public/platforms/{created['slug']}/reports").json()
    items = reports.get("items", reports)
    labels = [str(r.get("location_label") or "") for r in items]
    assert any(labels), "public reports should carry a coarse location label"
    joined = " ".join(labels)
    for ghost in ("仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"):
        assert ghost not in joined, f"{ghost} does not exist in 花蓮縣: {joined[:200]}"
