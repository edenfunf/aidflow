"""LINE group binding through the signed webhook, and staff pushes to the
bound group (needs a live database; LINE itself is never contacted)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid

from app.connectors import line
from app.core.config import settings

# generated per run so the value is never a literal in the repository
SECRET = "pytest-" + secrets.token_urlsafe(12)


def _signed(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode("utf-8")
    sig = base64.b64encode(hmac.new(SECRET.encode(), raw, hashlib.sha256).digest()).decode()
    return raw, {"X-Line-Signature": sig, "Content-Type": "application/json"}


def _group_id() -> str:
    # a valid LINE group id shape (C + 32 hex); the 0000 prefix marks test rows
    return "C0000" + uuid.uuid4().hex[:28]


def test_signature_verification_unit(monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", SECRET)
    raw, headers = _signed({"events": []})
    assert line.verify_signature(raw, headers["X-Line-Signature"])
    assert not line.verify_signature(raw + b" ", headers["X-Line-Signature"])
    assert not line.verify_signature(raw, None)


def test_webhook_rejects_unsigned_and_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "")
    assert client.post("/v1/line/webhook", content=b"{}").status_code == 503
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", SECRET)
    assert client.post("/v1/line/webhook", content=b"{}", headers={"X-Line-Signature": "bogus"}).status_code == 401


def test_bind_code_in_group_binds_platform_and_staff_push_goes_there(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", SECRET)
    status = client.get(f"/v1/platforms/{platform['id']}/line").json()
    code = status["bind_code"]
    assert status["bound"] is False and len(code) == 6
    group = _group_id()

    raw, headers = _signed({"events": [{"type": "join", "source": {"type": "group", "groupId": group}, "replyToken": "r1"}]})
    assert client.post("/v1/line/webhook", content=raw, headers=headers).json() == {"handled": 1}
    raw, headers = _signed({"events": [{"type": "message", "source": {"type": "group", "groupId": group},
                                        "replyToken": "r2", "message": {"type": "text", "text": "綁定 WRONG1"}}]})
    assert client.post("/v1/line/webhook", content=raw, headers=headers).json() == {"handled": 0}
    raw, headers = _signed({"events": [{"type": "message", "source": {"type": "group", "groupId": group},
                                        "replyToken": "r3", "message": {"type": "text", "text": f"綁定 {code.lower()}"}}]})
    assert client.post("/v1/line/webhook", content=raw, headers=headers).json() == {"handled": 1}
    bound = client.get(f"/v1/platforms/{platform['id']}/line").json()
    assert bound["bound"] is True and bound["group_id_masked"].startswith(group[:8])

    # with a token configured, a new report is pushed to exactly that group
    pushed: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "token")
    monkeypatch.setattr(line, "push_text", lambda to, text: pushed.append((to, text)) or "req-1")
    import threading

    class _Inline:  # run the worker inline so the test sees the push
        def __init__(self, target=None, args=(), **_):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(threading, "Thread", _Inline)
    client.post(f"/v1/public/platforms/{platform['slug']}/reports", json={
        "category": "landslide", "lat": 24.2001, "lon": 121.2001, "client_key": "line-1", "description": "邊坡滑落"})
    assert pushed and pushed[0][0] == group and "新災情通報" in pushed[0][1] and "/console/platforms/" in pushed[0][1]
    logs = client.get(f"/v1/platforms/{platform['id']}/notifications").json()["items"]
    assert any(n["channel"] == "line" and n["status"] == "sent" for n in logs)

    # leaving the group unbinds it
    raw, headers = _signed({"events": [{"type": "leave", "source": {"type": "group", "groupId": group}}]})
    client.post("/v1/line/webhook", content=raw, headers=headers)
    assert client.get(f"/v1/platforms/{platform['id']}/line").json()["bound"] is False


def test_manual_bind_validates_group_id(client, platform):
    assert client.put(f"/v1/platforms/{platform['id']}/line", json={"group_id": "not-a-group-id"}).status_code == 422
    group = _group_id()
    ok = client.put(f"/v1/platforms/{platform['id']}/line", json={"group_id": group})
    assert ok.status_code == 200 and ok.json()["bound"] is True
    test = client.post(f"/v1/platforms/{platform['id']}/line/test").json()
    assert test["result"] == "simulated"  # no token in tests: logged, never sent
    assert client.delete(f"/v1/platforms/{platform['id']}/line").json()["bound"] is False
