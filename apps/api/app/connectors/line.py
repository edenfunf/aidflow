"""LINE Official Account outbound connector (real Messaging API broadcast).

Broadcasts an approved message to all friends of the configured LINE OA. The OA
must be created once in the LINE console with Messaging API enabled; supply its
Channel Access Token via LINE_CHANNEL_ACCESS_TOKEN. When unset, ``is_configured()``
is False and the caller falls back to the simulated connector.
"""
from __future__ import annotations

import httpx

from app.connectors.base import ConnectorError
from app.core.config import settings

CONNECTOR_NAME = "line_messaging"

_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def is_configured() -> bool:
    return bool(settings.LINE_CHANNEL_ACCESS_TOKEN)


def broadcast(*, text: str, quick_replies: list[str] | None = None) -> dict:
    """Broadcast a text message (with optional quick-reply buttons) to all
    friends. Returns a result dict; raises ConnectorError on failure."""
    message: dict = {"type": "text", "text": text}
    items = [q for q in (quick_replies or []) if q][:13]  # LINE caps at 13
    if items:
        message["quickReply"] = {
            "items": [
                {
                    "type": "action",
                    "action": {"type": "message", "label": q[:20], "text": q},
                }
                for q in items
            ]
        }

    headers = {
        "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(
            _BROADCAST_URL, headers=headers, json={"messages": [message]}, timeout=20
        )
    except httpx.HTTPError as exc:
        raise ConnectorError(f"LINE 連線失敗：{exc}") from exc

    if resp.status_code >= 400:
        detail = _error_detail(resp)
        raise ConnectorError(f"LINE 推播失敗（{resp.status_code}）：{detail}")

    request_id = resp.headers.get("x-line-request-id")
    return {
        "connector": CONNECTOR_NAME,
        "status": "published",
        "external_ref": request_id,
        "url": None,  # a broadcast has no public permalink
        "detail": "已透過 LINE Messaging API 推播給所有好友。",
    }


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return body.get("message") or resp.text[:300]
    except Exception:
        return resp.text[:300]
