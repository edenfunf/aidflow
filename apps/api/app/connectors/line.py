"""LINE Messaging API connector — staff notifications to a county LINE group.

The bot (a LINE Official Account with Messaging API enabled) is invited into
the county's notification group. The group is bound to a platform through the
webhook (「綁定 <代碼>」, see line_service). New reports are then *pushed* to
that group id.

LINE_CHANNEL_ACCESS_TOKEN authorises pushes/replies; LINE_CHANNEL_SECRET
verifies webhook signatures. When the token is unset ``is_configured()`` is
False and callers record the notification as simulated.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

import httpx

from app.connectors.base import ConnectorError
from app.core.config import settings

CONNECTOR_NAME = "line_messaging"

_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
# LINE caps a text message at 5000 characters
_MAX_TEXT = 4900


def is_configured() -> bool:
    return bool(settings.LINE_CHANNEL_ACCESS_TOKEN)


def webhook_enabled() -> bool:
    return bool(settings.LINE_CHANNEL_SECRET)


def verify_signature(body: bytes, signature: str | None) -> bool:
    """X-Line-Signature = base64(HMAC-SHA256(channel secret, raw body))."""
    if not settings.LINE_CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(settings.LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode("ascii"), signature)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"}


def _post(url: str, body: dict) -> str | None:
    try:
        resp = httpx.post(url, headers=_headers(), json=body, timeout=15)
    except httpx.HTTPError as exc:
        raise ConnectorError(f"LINE 連線失敗：{exc}") from exc
    if resp.status_code >= 400:
        raise ConnectorError(f"LINE 推播失敗（{resp.status_code}）：{_error_detail(resp)}")
    return resp.headers.get("x-line-request-id")


def push_text(to: str, text: str) -> str | None:
    """Push a text message to a user / group id. Returns LINE's request id;
    raises ConnectorError on failure."""
    return _post(_PUSH_URL, {"to": to, "messages": [{"type": "text", "text": text[:_MAX_TEXT]}]})


def reply_text(reply_token: str, text: str) -> str | None:
    return _post(_REPLY_URL, {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:_MAX_TEXT]}]})


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return body.get("message") or resp.text[:300]
    except Exception:
        return resp.text[:300]
