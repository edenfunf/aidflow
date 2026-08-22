"""Test configuration.

Integration tests need a live PostgreSQL (DATABASE_URL). Unit tests for the
domain rules, clustering geometry, privacy transforms and connector
normalisers run without a database.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("MEDIA_ROOT", os.path.join(tempfile.gettempdir(), "aidflow-test-media"))
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("ADMIN_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
# tests are offline: force every upstream credential empty even when the
# developer shell has real keys exported
os.environ["CWA_API_KEY"] = ""
os.environ["NCDR_CAP_FEED_URL"] = ""
os.environ["TDX_CLIENT_ID"] = ""
os.environ["TDX_CLIENT_SECRET"] = ""

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def purge_test_platforms():
    """Tests share the developer database: remove everything they created
    so the home page / console never fill up with 測試平台-xxxx rows."""
    yield
    try:
        from sqlalchemy import or_, select

        from app.db.database import SessionLocal
        from app.db.models import Platform

        with SessionLocal() as db:
            rows = db.scalars(
                select(Platform).where(
                    or_(
                        Platform.name.like("測試平台-%"),
                        Platform.name.like("測試-%"),
                        Platform.name.in_(("bad", "草稿平台")),
                        Platform.configuration.op("@>")({"demo_key": "nantou-2026-heavy-rain-test"}),
                    )
                )
            ).all()
            for p in rows:
                db.delete(p)
            db.commit()
    except Exception:  # no database in unit-only runs
        pass


@pytest.fixture()
def platform(client) -> dict:
    """A fresh published platform for the standard Nantou heavy-rain brief."""
    brief = "南投縣仁愛鄉因豪雨造成道路坍方、土石流與積淹水，希望建立全民災情通報與即時處理平台。"
    plan = client.post("/v1/agent/plan", json={"message": brief}).json()
    draft = plan["draft"]
    draft["name"] = f"測試平台-{os.urandom(3).hex()}"
    resp = client.post("/v1/agent/execute", json=draft)
    assert resp.status_code == 201, resp.text
    return resp.json()["platform"]


@pytest.fixture(autouse=True)
def stub_network(monkeypatch):
    """Tests never hit OSRM or the Nantou CKAN: routes fall back to straight
    lines and fire stations come from the documented sample payload."""
    if os.environ.get("ALLOW_NETWORK_TESTS"):
        yield
        return
    from app.connectors import nantou_open_data, osrm
    from app.services import responder_service

    monkeypatch.setattr(osrm, "route", osrm.straight_line)
    monkeypatch.setattr(
        nantou_open_data, "fetch_fire_stations",
        lambda: nantou_open_data.map_fire_stations(nantou_open_data.SAMPLE_FIRE_STATIONS),
    )
    responder_service.clear_route_cache()
    yield
