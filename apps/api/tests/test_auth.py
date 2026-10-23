"""Login, lockout, token revocation and the role / permission matrix
(開發設計規劃書 伍) — needs a live database."""
from __future__ import annotations

import uuid
import secrets

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import EventOutbox, User
from app.services import auth_service

# generated per run: a literal here reads as a hardcoded credential to scanners
PASSWORD = "Pytest-" + secrets.token_urlsafe(12)
OTHER_PASSWORD = "Pytest-" + secrets.token_urlsafe(12)


def _make_user(role: str) -> User:
    with SessionLocal() as db:
        return auth_service.create_user(db, username=f"test-{role}-{uuid.uuid4().hex[:6]}", display_name=f"測試{role}",
                                        role=role, password=PASSWORD, actor="pytest", must_change_password=False)


def _login(client, username: str, password: str = PASSWORD):
    return client.post("/v1/auth/login", json={"username": username, "password": password})


def _headers(client, user: User) -> dict:
    resp = _login(client, user.username)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    yield


def test_login_required_when_auth_is_on(client, platform, auth_on):
    assert client.get("/v1/platforms").status_code == 401
    assert client.get(f"/v1/platforms/{platform['id']}/cases").status_code == 401
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/health").json()["auth_required"] is True
    # the public portal never needs a login
    assert client.get(f"/v1/public/platforms/{platform['slug']}/map").status_code == 200
    assert client.get("/v1/platforms", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_login_me_logout_and_audit(client, auth_on):
    officer = _make_user("officer")
    resp = _login(client, officer.username.upper())  # usernames are case-insensitive
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["role"] == "officer" and body["user"]["role_label"] == "承辦審核人員"
    assert "review_cases" in body["user"]["permissions"] and "manage_users" not in body["user"]["permissions"]
    h = {"Authorization": f"Bearer {body['token']}"}
    me = client.get("/v1/auth/me", headers=h).json()
    assert me["username"] == officer.username and me["display_name"] == officer.display_name
    assert client.post("/v1/auth/logout", headers=h).json() == {"ok": True}
    with SessionLocal() as db:
        types = set(db.scalars(select(EventOutbox.event_type).where(
            EventOutbox.payload["username"].astext == officer.username)).all())
    assert {"user.created", "auth.login", "auth.logout"} <= types


def test_wrong_password_locks_account_after_limit(client, auth_on, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MAX_FAILED_ATTEMPTS", 3)
    user = _make_user("officer")
    for _ in range(2):
        r = _login(client, user.username, "wrong-password")
        assert r.status_code == 401 and r.json()["detail"] == "帳號或密碼錯誤"
    locked = _login(client, user.username, "Pytest-wrong-" + secrets.token_urlsafe(6))
    assert locked.status_code == 401 and "locked_until" in locked.json()["detail"]
    # even the correct credentials are refused while locked
    assert _login(client, user.username).status_code == 401
    # an unknown username fails the same way (no account enumeration)
    assert _login(client, "test-nobody-here", secrets.token_urlsafe(8)).json()["detail"] == "帳號或密碼錯誤"


def test_password_change_revokes_old_tokens(client, auth_on):
    user = _make_user("supervisor")
    old = _headers(client, user)
    weak = client.post("/v1/auth/password", headers=old, json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422
    changed = client.post("/v1/auth/password", headers=old,
                          json={"current_password": PASSWORD, "new_password": OTHER_PASSWORD})
    assert changed.status_code == 200
    assert client.get("/v1/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {changed.json()['token']}"}
    assert client.get("/v1/auth/me", headers=new).status_code == 200


def test_role_permission_matrix(client, platform, auth_on):
    officer, supervisor, admin = _make_user("officer"), _make_user("supervisor"), _make_user("admin")
    ho, hs, ha = _headers(client, officer), _headers(client, supervisor), _headers(client, admin)
    slug = platform["slug"]
    body = {"category": "flooding", "lat": 24.1001, "lon": 121.2001, "reporter_role": "citizen",
            "reporter_contact": "0955000111", "reporter_name": "測試民眾"}
    client.post(f"/v1/public/platforms/{slug}/reports", json={**body, "client_key": "perm-1"})
    case_id = client.post(f"/v1/public/platforms/{slug}/reports", json={
        **body, "client_key": "perm-2", "reporter_contact": None, "reporter_name": None}).json()["case_id"]
    assert case_id

    # everyone with a console role sees the dashboard and the case
    for h in (ho, hs, ha):
        assert client.get(f"/v1/platforms/{platform['id']}/overview", headers=h).status_code == 200
        assert client.get(f"/v1/cases/{case_id}", headers=h).status_code == 200

    # 個資: officer and supervisor see it (logged); the administrator does not
    officer_view = client.get(f"/v1/cases/{case_id}", headers=ho).json()
    assert officer_view["pii_visible"] and any(r["reporter_contact"] == "0955000111" for r in officer_view["reports"])
    admin_view = client.get(f"/v1/cases/{case_id}", headers=ha).json()
    assert not admin_view["pii_visible"] and all(r["reporter_contact"] is None for r in admin_view["reports"])
    assert any(r["pii_hidden"] for r in admin_view["reports"])
    with SessionLocal() as db:
        viewed = db.scalars(select(EventOutbox).where(EventOutbox.event_type == "pii.viewed",
                                                      EventOutbox.payload["case_id"].astext == case_id)).all()
    assert {e.payload["username"] for e in viewed} >= {officer.display_name, supervisor.display_name}
    assert admin.display_name not in {e.payload["username"] for e in viewed}

    # only the officer reviews; supervisor and admin are read-only on cases
    assert client.post(f"/v1/cases/{case_id}/review", headers=hs, json={"decision": "emic"}).status_code == 403
    assert client.post(f"/v1/cases/{case_id}/review", headers=ha, json={"decision": "emic"}).status_code == 403
    done = client.post(f"/v1/cases/{case_id}/review", headers=ho, json={"decision": "emic"})
    assert done.status_code == 200 and done.json()["case"]["reviewed_by"] == officer.display_name

    # platform management, LINE binding and accounts are the administrator's
    patch = {"cluster_policy": {"radius_meters": 120}}
    assert client.patch(f"/v1/platforms/{platform['id']}", headers=ho, json=patch).status_code == 403
    assert client.patch(f"/v1/platforms/{platform['id']}", headers=ha, json=patch).status_code == 200
    assert client.get(f"/v1/platforms/{platform['id']}/line", headers=ho).json()["bind_code"] is None
    assert client.get(f"/v1/platforms/{platform['id']}/line", headers=ha).json()["bind_code"]
    assert client.get("/v1/users", headers=ho).status_code == 403
    assert client.get("/v1/users", headers=ha).status_code == 200

    # security audit: supervisor and admin, not the officer
    assert client.get("/v1/admin/audit", headers=ho).status_code == 403
    audit = client.get("/v1/admin/audit", headers=hs, params={"kind": "pii"})
    assert audit.status_code == 200 and all(e["event_type"].startswith("pii.") for e in audit.json()["items"])
    # the platform feed never carries security events
    feed = client.get(f"/v1/platforms/{platform['id']}/audit", headers=ho).json()["items"]
    assert not any(e["event_type"].startswith(("pii.", "auth.")) for e in feed)


def test_admin_manages_accounts(client, auth_on):
    admin = _make_user("admin")
    ha = _headers(client, admin)
    name = f"test-new-{uuid.uuid4().hex[:6]}"
    weak = client.post("/v1/users", headers=ha, json={"username": name, "display_name": "新承辦", "role": "officer", "password": "short"})
    assert weak.status_code == 422
    bad_role = client.post("/v1/users", headers=ha, json={"username": name, "display_name": "新承辦", "role": "boss", "password": PASSWORD})
    assert bad_role.status_code == 422
    created = client.post("/v1/users", headers=ha, json={"username": name, "display_name": "新承辦", "role": "officer", "password": PASSWORD})
    # AUTH_FORCE_PASSWORD_CHANGE is off by default: the user changes it in 帳號設定 instead
    assert created.status_code == 201 and created.json()["must_change_password"] is False
    uid = created.json()["id"]
    assert client.post("/v1/users", headers=ha, json={"username": name, "display_name": "x", "role": "officer", "password": PASSWORD}).status_code == 422

    token = _login(client, name).json()["token"]
    off = client.patch(f"/v1/users/{uid}", headers=ha, json={"active": False})
    assert off.status_code == 200 and off.json()["active"] is False
    assert client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert _login(client, name).status_code == 401
    # an administrator cannot lock themselves out
    assert client.patch(f"/v1/users/{admin.id}", headers=ha, json={"active": False}).status_code == 422
    assert client.patch(f"/v1/users/{admin.id}", headers=ha, json={"role": "officer"}).status_code == 422


def test_bootstrap_admin_only_when_no_accounts(monkeypatch):
    monkeypatch.setattr(settings, "INITIAL_ADMIN_PASSWORD", "Bootstrap-2026-x")
    _make_user("officer")  # there is at least one account now
    with SessionLocal() as db:
        assert auth_service.bootstrap_admin(db) is None


def test_password_policy_unit():
    with pytest.raises(auth_service.AccountError):
        auth_service.validate_password("alllowercaseletters")
    with pytest.raises(auth_service.AccountError):
        auth_service.validate_password("Short1")
    auth_service.validate_password("Longer-pass-1")
    h = auth_service.hash_password("Longer-pass-1")
    assert h.startswith("$argon2") and "Longer" not in h
    assert auth_service.verify_password(h, "Longer-pass-1") and not auth_service.verify_password(h, "nope")
