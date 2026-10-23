"""Test configuration.

Integration tests need a live PostgreSQL (DATABASE_URL). Unit tests for the
domain rules, clustering geometry, privacy transforms and connector
normalisers run without a database.

The suite runs with AUTH_REQUIRED=false (an unauthenticated request acts as a
開發模式 principal) and rate limiting off; test_auth.py switches login back on
to exercise the real gate.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("MEDIA_ROOT", os.path.join(tempfile.gettempdir(), "aidflow-test-media"))
os.environ.setdefault("DEMO_MODE", "true")
os.environ["AUTH_REQUIRED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["INITIAL_ADMIN_PASSWORD"] = ""
# tests are offline: force every upstream credential empty even when the
# developer shell has real keys exported
os.environ["CWA_API_KEY"] = ""
os.environ["NCDR_CAP_FEED_URL"] = ""
os.environ["TDX_CLIENT_ID"] = ""
os.environ["TDX_CLIENT_SECRET"] = ""
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = ""
os.environ["LINE_CHANNEL_SECRET"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["EMIC_SUBMIT_URL"] = ""

import pytest  # noqa: E402

TEST_USER_PREFIX = "test-"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def purge_test_data():
    """Tests share the developer database: remove everything they created
    so the home page / console never fill up with 測試平台-xxxx rows."""
    yield
    try:
        from sqlalchemy import or_, select

        from app.db.database import SessionLocal
        from app.db.models import LineGroup, Platform, User

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
            for u in db.scalars(select(User).where(User.username.like(f"{TEST_USER_PREFIX}%"))).all():
                db.delete(u)
            for g in db.scalars(select(LineGroup).where(LineGroup.group_id.like("C0000%"))).all():
                db.delete(g)
            db.commit()
    except Exception:  # no database in unit-only runs
        pass


BRIEF_NAME = "南投縣仁愛鄉豪雨土石流"


@pytest.fixture()
def platform(client) -> dict:
    """A fresh published Nantou heavy-rain / landslide / flood platform."""
    body = {
        "name": f"測試平台-{os.urandom(3).hex()}",
        "hazards": ["heavy_rain", "landslide", "flood"],
        "county": "南投縣",
        "towns": ["仁愛鄉"],
        "publish": True,
    }
    resp = client.post("/v1/platforms", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(autouse=True)
def stub_network(monkeypatch):
    """Tests never hit the Nantou CKAN: fire stations come from the documented
    sample payload."""
    if os.environ.get("ALLOW_NETWORK_TESTS"):
        yield
        return
    from app.connectors import nantou_open_data

    monkeypatch.setattr(
        nantou_open_data, "fetch_fire_stations",
        lambda: nantou_open_data.map_fire_stations(nantou_open_data.SAMPLE_FIRE_STATIONS),
    )
    yield
