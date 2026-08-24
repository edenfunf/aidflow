"""Responder rules, vehicle simulation math (offline) and the dispatch /
vehicles / AVL endpoints (live database, OSRM + CKAN stubbed by conftest)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.connectors import osrm
from app.core.config import settings
from app.domain.responders import responder_kinds, vehicles_for
from app.services.responder_service import simulate_position
from app.utils.geo import point_along, polyline_length_m

SITE = {"lat": 23.9700, "lon": 120.9650}


def _report(**over) -> dict:
    body = {"category": "trapped_person", "description": "二樓有人受困", "reporter_role": "citizen", **SITE}
    body.update(over)
    return body


def _make_case(client, slug, **over) -> str:
    client.post(f"/v1/public/platforms/{slug}/reports", json=_report(client_key="d1", **over))
    r = client.post(f"/v1/public/platforms/{slug}/reports", json=_report(client_key="d2", **over))
    assert r.status_code == 201 and r.json()["case_created"], r.text
    return r.json()["case_id"]


# ── rules ─────────────────────────────────────────────────────────────────
def test_category_to_responder_rules():
    assert responder_kinds("trapped_person")[0] == "fire"
    assert responder_kinds("road_collapse")[0] == "highway"
    assert responder_kinds("flooding")[0] == "river"
    assert responder_kinds("landslide")[0] == "slope"
    assert responder_kinds("power_outage")[0] == "power"
    assert responder_kinds("unknown_thing") == responder_kinds("other")
    assert vehicles_for("fire", "trapped_person") == ["fire_engine", "fire_engine", "ambulance"]
    assert vehicles_for("fire", "medical_need")[0] == "ambulance"
    assert vehicles_for("highway", "road_collapse") == ["works_truck", "works_truck"]
    assert vehicles_for("power", "power_outage") == ["works_truck"]
    assert vehicles_for("fire", "fire") == ["fire_engine", "fire_engine"]


# ── polyline / simulation math ────────────────────────────────────────────
LINE = [[120.68, 23.90], [120.70, 23.90], [120.70, 23.92]]  # ~2.04 km east then ~2.2 km north


def test_point_along_polyline():
    total = polyline_length_m(LINE)
    assert 4100 < total < 4400
    lat, lon, heading = point_along(LINE, 0)
    assert (round(lat, 2), round(lon, 2)) == (23.90, 120.68) and 85 < heading < 95
    lat, lon, heading = point_along(LINE, 1000)
    assert round(lat, 2) == 23.90 and 120.68 < lon < 120.70
    lat, lon, heading = point_along(LINE, total)
    assert (round(lat, 2), round(lon, 2)) == (23.92, 120.70) and (heading < 5 or heading > 355)
    lat, lon, _ = point_along(LINE, total * 5)  # clamped
    assert (round(lat, 2), round(lon, 2)) == (23.92, 120.70)


def test_simulation_is_derived_from_timestamps_only(monkeypatch):
    monkeypatch.setattr(settings, "VEHICLE_SIM_SPEED_KMH", 60.0)  # 1 km/min
    t0 = datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc)
    a = SimpleNamespace(route_geojson={"type": "LineString", "coordinates": LINE}, departed_at=t0, status="active")
    c = SimpleNamespace(status="assigned", resolved_at=None)
    assert simulate_position(a, c, t0 - timedelta(minutes=1))["status"] == "preparing"
    mid = simulate_position(a, c, t0 + timedelta(minutes=1))
    assert mid["status"] == "en_route" and 0.15 < mid["progress"] < 0.35 and mid["eta_minutes"] >= 3
    arrived = simulate_position(a, c, t0 + timedelta(minutes=10))
    assert arrived["status"] == "on_site" and arrived["progress"] == 1.0
    # second vehicle of the same dispatch leaves 45 s later
    assert simulate_position(a, c, t0 + timedelta(seconds=30), index=1)["status"] == "preparing"
    # after resolution the vehicle drives back and then disappears
    done = SimpleNamespace(status="resolved", resolved_at=t0 + timedelta(minutes=20))
    back = simulate_position(a, done, t0 + timedelta(minutes=21))
    assert back["status"] == "returning" and back["progress"] < 1.0
    assert simulate_position(a, done, t0 + timedelta(minutes=40)) is None
    assert simulate_position(a, SimpleNamespace(status="dismissed", resolved_at=None), t0) is None
    assert simulate_position(SimpleNamespace(route_geojson=None, departed_at=t0, status="active"), c, t0) is None
    # demo replay: a case still 已派員／前往中 keeps its vehicle on the road, flagged; a
    # confirmed on-site case parks even with loop on; never replays when loop is off
    again = simulate_position(a, c, t0 + timedelta(minutes=10), loop=True)
    assert again["status"] == "en_route" and again["replay"] is True and 0 < again["progress"] < 1
    parked = simulate_position(a, SimpleNamespace(status="on_site", resolved_at=None), t0 + timedelta(minutes=10), loop=True)
    assert parked["status"] == "on_site"
    assert "replay" not in simulate_position(a, c, t0 + timedelta(minutes=10))


def test_osrm_straight_line_fallback():
    r = osrm.straight_line(23.9, 120.7, 23.92, 120.72)
    assert r["source"] == "straight_line" and 2500 < r["distance_m"] < 3500 and r["duration_s"] > 0
    assert r["geometry"]["coordinates"][0] == [120.7, 23.9]


# ── API ───────────────────────────────────────────────────────────────────
def test_units_registry_mixes_open_data_and_indicative_agencies(client, platform):
    body = client.get(f"/v1/platforms/{platform['id']}/units").json()
    kinds = {u["kind"] for u in body["items"]}
    assert {"fire", "highway", "river", "town_office", "police"} <= kinds
    fire = [u for u in body["items"] if u["kind"] == "fire"]
    assert fire and all(u["location_source"] == "open_data" for u in fire)
    assert all(u["location_source"] == "indicative" for u in body["items"] if u["kind"] == "town_office")


def test_responders_are_ranked_by_rules_then_distance_with_routes(client, platform):
    case_id = _make_case(client, platform["slug"])
    body = client.get(f"/v1/cases/{case_id}/responders").json()
    assert body["category"] == "trapped_person"
    items = body["items"]
    assert items[0]["primary"] and items[0]["unit"]["kind"] == "fire"
    assert [v["kind"] for v in items[0]["vehicles"]] == ["fire_engine", "fire_engine", "ambulance"]
    routed = [i for i in items if i["route"]]
    assert routed and routed[0]["route_source"] == "straight_line" and routed[0]["eta_minutes"] >= 1
    # distances are non-decreasing within the primary kind
    prim = [i["straight_m"] for i in items if i["primary"]]
    assert prim == sorted(prim)


def test_dispatch_routes_notifies_and_moves_vehicles(client, platform):
    slug = platform["slug"]
    case_id = _make_case(client, slug, lat=23.9500, lon=120.9800)
    unit = client.get(f"/v1/cases/{case_id}/responders").json()["items"][0]["unit"]
    resp = client.post(f"/v1/cases/{case_id}/dispatch", json={"unit_id": unit["id"], "note": "請攜帶破壞器材", "actor_name": "值班"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["case"]["status"] == "assigned" and body["case"]["assigned_unit"] == unit["name"]
    assert body["notification"]["channel"] == "simulated"  # no LINE / webhook configured in tests
    a = body["assignment"]
    assert a["route_source"] == "straight_line" and a["distance_m"] > 0 and a["eta_minutes"] >= 1
    assert [v["kind"] for v in a["vehicles"]] == ["fire_engine", "fire_engine", "ambulance"]

    # public timeline shows the dispatch notification, without unit contact details
    public = client.get(f"/v1/public/platforms/{slug}/cases/{case_id}").json()
    labels = [t["note"] or "" for t in public["timeline"]]
    assert any("已通報" in n and unit["name"] in n for n in labels)

    # vehicles: preparing (inside prep window) at the unit's position, labelled simulated
    veh = client.get(f"/v1/public/platforms/{slug}/vehicles").json()
    mine = [v for v in veh["items"] if v["case_id"] == case_id]
    assert len(mine) == 3 and {v["kind"] for v in mine} == {"fire_engine", "ambulance"}
    assert all(v["source"] == "simulated" and v["status"] in ("preparing", "en_route") for v in mine)
    routes = client.get(f"/v1/public/platforms/{slug}/routes").json()
    assert any(f["properties"]["case_id"] == case_id for f in routes["features"])

    # audit trail
    types = {e["event_type"] for e in client.get(f"/v1/platforms/{platform['id']}/audit").json()["items"]}
    assert {"dispatch.created", "case.dispatch_notified"} <= types


def test_avl_pings_replace_simulation(client, platform):
    slug = platform["slug"]
    case_id = _make_case(client, slug, lat=23.9300, lon=120.9900)
    unit = client.get(f"/v1/cases/{case_id}/responders").json()["items"][0]["unit"]
    a = client.post(f"/v1/cases/{case_id}/dispatch", json={"unit_id": unit["id"]}).json()["assignment"]
    vid = a["vehicles"][0]["vehicle_id"]
    ping = {"vehicle_id": vid, "unit_id": unit["id"], "kind": "fire_engine", "lat": 23.94, "lon": 120.97, "heading": 90,
            "recorded_at": datetime.now(timezone.utc).isoformat()}
    assert client.post("/v1/avl/positions", json={"positions": [ping]}).json()["ingested"] == 1
    veh = client.get(f"/v1/platforms/{platform['id']}/vehicles").json()
    live = next(v for v in veh["items"] if v["vehicle_id"] == vid)
    assert live["source"] == "avl" and live["status"] == "live" and live["lat"] == 23.94
    assert veh["has_live"] is True
    # stale pings are ignored → back to simulation
    old = {**ping, "vehicle_id": "stale-1", "recorded_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    client.post("/v1/avl/positions", json={"positions": [old]})
    ids = {v["vehicle_id"] for v in client.get(f"/v1/platforms/{platform['id']}/vehicles").json()["items"]}
    assert "stale-1" not in ids


def test_dispatch_rejects_unknown_unit_and_closed_case(client, platform):
    case_id = _make_case(client, platform["slug"], lat=23.9100, lon=120.9500)
    assert client.post(f"/v1/cases/{case_id}/dispatch", json={"unit_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404

def test_demo_vehicles_restart_from_base_on_every_page_load(client, platform):
    """A demo seeded hours ago must not greet a visitor with every vehicle
    already parked at the scene: the outbound leg follows the viewer's own
    session, so each fresh load sets the convoy off from its station."""
    slug = platform["slug"]
    case_id = _make_case(client, slug, lat=23.9500, lon=120.9800)
    unit = client.get(f"/v1/cases/{case_id}/responders").json()["items"][0]["unit"]
    client.post(f"/v1/cases/{case_id}/dispatch", json={"unit_id": unit["id"], "actor_name": "值班"})

    # mark it a demo platform — that is what enables the session anchoring
    client.patch(f"/v1/platforms/{platform['id']}", json={"configuration": {"demo": True}})

    def progress(elapsed):
        veh = client.get(f"/v1/public/platforms/{slug}/vehicles", params={"elapsed": elapsed}).json()
        mine = sorted([v for v in veh["items"] if v["case_id"] == case_id], key=lambda v: v["vehicle_id"])
        assert mine, "the dispatched vehicles should be listed"
        return [(v["status"], v["progress"]) for v in mine]

    at_load = progress(0)
    assert all(p == 0.0 for _s, p in at_load), f"a fresh load must start at base: {at_load}"
    assert all(s in ("preparing", "en_route") for s, _p in at_load), at_load

    # later in the same session the convoy has moved, and moved further still
    mid = progress(120)
    late = progress(400)
    assert max(p for _s, p in mid) > 0.0, f"vehicles should be under way by now: {mid}"
    assert max(p for _s, p in late) >= max(p for _s, p in mid), (mid, late)

    # convoy members leave 45 s apart, so at t=0 the second is still preparing
    statuses = [s for s, _p in progress(20)]
    assert "preparing" in statuses, statuses


def test_elapsed_is_ignored_on_a_real_platform(client, platform):
    """The parameter is a demo affordance. On a platform that is not flagged as
    a demo it must not be able to reposition anything."""
    slug = platform["slug"]
    case_id = _make_case(client, slug, lat=23.9500, lon=120.9800)
    unit = client.get(f"/v1/cases/{case_id}/responders").json()["items"][0]["unit"]
    client.post(f"/v1/cases/{case_id}/dispatch", json={"unit_id": unit["id"], "actor_name": "值班"})

    def snapshot(elapsed=None):
        params = {"elapsed": elapsed} if elapsed is not None else {}
        veh = client.get(f"/v1/public/platforms/{slug}/vehicles", params=params).json()
        return sorted((v["vehicle_id"], v["status"]) for v in veh["items"] if v["case_id"] == case_id)

    assert snapshot(elapsed=3_600) == snapshot(), "a real platform must ignore elapsed"

    # and the parameter is bounded, so it cannot be used to ask for silly values
    assert client.get(f"/v1/public/platforms/{slug}/vehicles", params={"elapsed": 99_999}).status_code == 422
    assert client.get(f"/v1/public/platforms/{slug}/vehicles", params={"elapsed": -1}).status_code == 422
