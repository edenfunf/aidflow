"""Planner → approval → deterministic composer (needs a live database).

Runs with the AI layer disabled so it exercises the rules fallback — the
path that must always work."""
from __future__ import annotations

import uuid

from app.core.config import settings
from app.modules import registry

BRIEF = "南投縣仁愛鄉因豪雨造成道路坍方、土石流與積淹水，希望建立全民災情通報與即時處理平台。"


def test_plan_understands_brief_and_proposes_modules(client):
    resp = client.post("/v1/agent/plan", json={"message": BRIEF})
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["intent_mode"] in {"ai", "rules"}
    assert plan["scenario"]["region"]["county"] == "南投縣"
    assert "仁愛鄉" in plan["scenario"]["region"]["towns"]
    assert {"heavy_rain", "landslide", "flood"} <= set(plan["scenario"]["hazards"])
    recommended = {m["id"] for m in plan["suggested_modules"] if m["recommended"]}
    assert set(registry.core_ids()) - {l.id for l in registry.layers()} <= recommended
    layers = {l["key"] for l in plan["suggested_layers"] if l["recommended"]}
    assert {"incident_cases", "report_clusters", "citizen_reports", "rainfall", "water", "landslide",
            "flooding", "shelter", "fire_station", "official_alert"} <= layers
    cats = [c["key"] for c in plan["suggested_report_categories"] if c["recommended"]]
    assert cats[:3] == ["road_collapse", "landslide", "flooding"]
    assert "gas_leak" not in cats
    policy = plan["suggested_cluster_policy"]
    assert policy["required_unique_reporters"] == 2 and policy["radius_meters"] >= 100
    assert plan["draft"]["hazards"] and plan["draft"]["county"] == "南投縣"
    # honest about layers that need keys
    cwa_layer = next(l for l in plan["suggested_layers"] if l["key"] == "rainfall")
    assert cwa_layer["live"] is False
    assert plan["reasons"]


def test_plan_does_not_create_a_platform(client):
    before = client.get("/v1/platforms").json()["total"]
    client.post("/v1/agent/plan", json={"message": BRIEF})
    assert client.get("/v1/platforms").json()["total"] == before


def test_execute_composes_platform_with_core_modules_and_dependencies(client):
    plan = client.post("/v1/agent/plan", json={"message": BRIEF}).json()
    draft = plan["draft"]
    draft["name"] = f"測試-{uuid.uuid4().hex[:6]}"
    # human trims the selection: drop photo_upload, keep the layers
    draft["modules"] = [m for m in draft["modules"] if m not in ("photo_upload", "trend_visualization")]
    resp = client.post("/v1/agent/execute", json=draft)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    platform = body["platform"]
    assert platform["status"] == "published" and platform["slug"].startswith("nantou")
    assert "photo_upload" not in platform["modules"]
    assert set(registry.core_ids()) <= set(platform["modules"])
    # the water layer pulls its connector dependency in
    assert "water" in platform["layers"] and "wra_connector" in platform["modules"]
    assert platform["configuration"]["cluster_policy"]["required_unique_reporters"] == 2
    assert body["public_url"].endswith(f"/p/{platform['slug']}")
    configs = {m["module_id"]: m for m in platform["module_configs"]}
    assert configs["two_report_trigger"]["config"]["radius_meters"] == draft["cluster_policy"]["radius_meters"]

    public = client.get(f"/v1/public/platforms/{platform['slug']}").json()
    assert [c["key"] for c in public["report_categories"]][:2] == ["road_collapse", "landslide"]
    assert public["report_categories"][-1]["key"] == "other"
    assert public["cluster_policy"]["required_unique_reporters"] == 2
    assert "brief" not in public


def test_execute_rejects_unknown_module_and_layer(client):
    draft = {"name": "bad", "hazards": ["flood"], "county": "南投縣", "towns": [], "modules": ["not_a_module"]}
    assert client.post("/v1/agent/execute", json=draft).status_code == 422
    draft = {"name": "bad", "hazards": ["flood"], "county": "南投縣", "towns": [], "layers": ["nope"]}
    assert client.post("/v1/agent/execute", json=draft).status_code == 422
    draft = {"name": "bad", "hazards": ["volcano"], "county": "南投縣", "towns": []}
    assert client.post("/v1/agent/execute", json=draft).status_code == 422


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


def test_api_key_gate_protects_console_but_not_public(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-key")
    try:
        assert client.get("/v1/platforms").status_code == 401
        assert client.post("/v1/agent/plan", json={"message": BRIEF}).status_code == 401
        assert client.get(f"/v1/platforms/{platform['id']}/reports").status_code == 401
        assert client.get("/v1/platforms", headers={"X-API-Key": "secret-key"}).status_code == 200
        assert client.get("/v1/health").status_code == 200
        assert client.get(f"/v1/public/platforms/{platform['slug']}").status_code == 200
        assert client.get(f"/v1/public/platforms/{platform['slug']}/situation").status_code == 200
    finally:
        monkeypatch.setattr(settings, "ADMIN_API_KEY", "")


def test_module_catalogue_and_connectors(client):
    body = client.get("/v1/modules").json()
    assert body["total"] == len(registry.all())
    domains = {d["key"] for d in client.get("/v1/modules/domains").json()["items"]}
    assert {"reporting", "processing", "dispatch", "visualization", "official_data", "notification",
            "privacy", "public_transparency", "analytics"} == domains
    layers = client.get("/v1/modules", params={"module_type": "layer"}).json()["items"]
    assert all(m["layer_key"] for m in layers)
    conns = {c["id"]: c for c in client.get("/v1/connectors").json()["items"]}
    assert conns["cwa_connector"]["status"] == "disabled"
    assert conns["moi_shelter_connector"]["status"] == "ready"
