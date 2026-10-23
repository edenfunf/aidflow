"""Named-disaster platform creation (G-10) — deterministic composer, no model
(needs a live database)."""
from __future__ import annotations

import uuid

from app.core.config import settings
from app.modules import registry


def test_preview_suggests_hazards_from_the_disaster_name(client):
    resp = client.post("/v1/platforms/preview", json={"name": "115 年 0903 颱風豪雨土石流", "county": "南投縣", "towns": ["仁愛鄉"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"typhoon", "heavy_rain", "landslide"} <= set(body["detected_hazards"])
    assert body["hazards"] == body["detected_hazards"]
    cats = [c["key"] for c in body["report_categories"]]
    assert "road_collapse" in cats and cats[-1] == "other" and "gas_leak" not in cats
    assert {"incident_cases", "rainfall", "debris_flow", "fire_station"} <= set(body["layers"])
    # an explicit hazard choice wins over the name
    quake = client.post("/v1/platforms/preview", json={"name": "0903 豪雨", "hazards": ["earthquake"], "county": "花蓮縣"}).json()
    assert quake["hazards"] == ["earthquake"] and "gas_leak" in [c["key"] for c in quake["report_categories"]]


def test_options_list_hazards_and_regions(client):
    body = client.get("/v1/platforms/options").json()
    assert {"key": "heavy_rain", "label": "豪雨"} in body["hazards"]
    nantou = next(r for r in body["regions"] if r["county"] == "南投縣")
    assert "仁愛鄉" in nantou["towns"]


def test_create_composes_platform_with_core_modules(client):
    body = {"name": f"測試-{uuid.uuid4().hex[:6]}", "hazards": ["heavy_rain", "flood"], "county": "南投縣",
            "towns": ["埔里鎮"], "publish": True}
    resp = client.post("/v1/platforms", json=body)
    assert resp.status_code == 201, resp.text
    platform = resp.json()
    assert platform["status"] == "published" and platform["slug"].startswith("nantou")
    assert set(registry.core_ids()) <= set(platform["modules"])
    assert {"case_review", "emic_report", "community_handling", "line_group_notify", "progress_subscription"} <= set(platform["modules"])
    assert "water" in platform["layers"] and "wra_connector" in platform["modules"]
    assert platform["configuration"]["cluster_policy"]["required_unique_reporters"] == 2
    assert platform["public_url"].endswith(f"/p/{platform['slug']}")
    assert platform["embed_url"].endswith(f"/embed/{platform['slug']}")

    public = client.get(f"/v1/public/platforms/{platform['slug']}").json()
    assert public["report_categories"][-1]["key"] == "other"
    assert "brief" not in public and "town_centers" not in public


def test_create_rejects_unknown_module_layer_and_hazard(client):
    base = {"name": "bad", "county": "南投縣", "towns": []}
    assert client.post("/v1/platforms", json={**base, "hazards": ["flood"], "modules": ["not_a_module"]}).status_code == 422
    assert client.post("/v1/platforms", json={**base, "hazards": ["flood"], "layers": ["nope"]}).status_code == 422
    assert client.post("/v1/platforms", json={**base, "hazards": ["volcano"]}).status_code == 422


def test_draft_platform_is_not_public_until_published(client):
    draft = {"name": "草稿平台", "hazards": ["flood"], "county": "南投縣", "towns": ["埔里鎮"], "publish": False}
    created = client.post("/v1/platforms", json=draft).json()
    assert created["status"] == "draft"
    assert client.get(f"/v1/public/platforms/{created['slug']}").status_code == 404
    published = client.post(f"/v1/platforms/{created['id']}/status", json={"status": "published"}).json()
    assert published["published_at"]
    assert client.get(f"/v1/public/platforms/{created['slug']}").status_code == 200


def test_cluster_policy_is_configurable_after_creation(client, platform):
    resp = client.patch(f"/v1/platforms/{platform['id']}", json={"cluster_policy": {"required_unique_reporters": 3, "radius_meters": 250}})
    assert resp.status_code == 200
    cfg = resp.json()["configuration"]["cluster_policy"]
    assert cfg["required_unique_reporters"] == 3 and cfg["radius_meters"] == 250
    assert cfg["time_window_minutes"]  # default preserved


def test_login_protects_console_but_not_public(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    assert client.get("/v1/platforms").status_code == 401
    assert client.get(f"/v1/platforms/{platform['id']}/reports").status_code == 401
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/health").json()["auth_required"] is True
    assert client.get(f"/v1/public/platforms/{platform['slug']}").status_code == 200
    assert client.get(f"/v1/public/platforms/{platform['slug']}/situation").status_code == 200


def test_module_catalogue_and_connectors(client):
    body = client.get("/v1/modules").json()
    assert body["total"] == len(registry.all())
    domains = {d["key"] for d in client.get("/v1/modules/domains").json()["items"]}
    assert {"reporting", "processing", "handling", "visualization", "official_data", "notification",
            "privacy", "public_transparency", "analytics"} == domains
    layers = client.get("/v1/modules", params={"module_type": "layer"}).json()["items"]
    assert all(m["layer_key"] for m in layers)
    conns = {c["id"]: c for c in client.get("/v1/connectors").json()["items"]}
    assert conns["cwa_connector"]["status"] == "disabled"
    assert conns["moi_shelter_connector"]["status"] == "ready"


def test_removed_features_are_gone(client, platform):
    assert client.post("/v1/agent/plan", json={"message": "x"}).status_code == 404
    assert client.get(f"/v1/platforms/{platform['id']}/vehicles").status_code == 404
    assert client.get(f"/v1/public/platforms/{platform['slug']}/routes").status_code == 404
    assert client.post("/v1/avl/positions", json={}).status_code == 404
