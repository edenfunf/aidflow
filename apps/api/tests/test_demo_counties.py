"""Seed the demo into several very different counties through the real pipeline."""
import pytest

COUNTIES = ["台北市", "澎湖縣", "台東縣", "高雄市", "宜蘭縣"]


@pytest.mark.parametrize("county", COUNTIES)
def test_demo_translates_cleanly(client, county):
    from app.utils.geo import TOWN_CENTROIDS, haversine_m

    town = sorted(TOWN_CENTROIDS[county])[0]
    draft = {"name": f"測試-{county}示範", "county": county, "towns": [town],
             "hazards": ["flood"], "report_categories": ["flooding", "road_collapse", "landslide",
                                                         "bridge_damage", "trapped_person", "other"]}
    created = client.post("/v1/agent/execute", json=draft).json()["platform"]
    r = client.post(f"/v1/platforms/{created['id']}/demo").json()
    assert r["seeded"] is True, r
    assert r["cases"] >= 8, f"{county}: only {r['cases']} cases — sites merged"

    items = client.get(f"/v1/public/platforms/{created['slug']}/reports").json()
    items = items.get("items", items)
    labels = [str(i.get("location_label") or "") for i in items]
    assert any(labels)
    for ghost in ("仁愛鄉", "信義鄉", "埔里鎮", "國姓鄉", "水里鄉"):
        assert ghost not in " ".join(labels), f"{county} invented {ghost}"

    anchors = TOWN_CENTROIDS[county]
    pts = [(i["lat"], i["lon"]) for i in items if i.get("lat") is not None]
    assert pts
    worst = max(min(haversine_m(la, lo, a, b) for a, b in anchors.values()) for la, lo in pts)
    assert worst <= 7_000, f"{county}: a point sits {worst/1000:.1f} km from any township"

    # every report must be attributed to a township of THIS county
    towns = {i.get("town") for i in items if i.get("town")}
    assert towns, f"{county}: no report got a township"
    assert towns <= set(anchors), f"{county}: foreign townships {towns - set(anchors)}"
