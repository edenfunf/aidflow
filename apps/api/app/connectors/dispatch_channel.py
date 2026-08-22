"""Outbound dispatch notification — how a responder unit is told about a case.

Channels, tried in this order:
  1. LINE push to the unit's configured LINE user/group id (real Messaging API)
  2. a generic webhook (``DISPATCH_WEBHOOK_URL``) that a county EOC / CAD
     system can receive (JSON POST)
  3. simulated — recorded in the audit trail only
The message carries no reporter PII beyond what the unit needs (location,
category, counts, public summary, photo links).
"""
from __future__ import annotations

import httpx

from app.connectors.base import ConnectorError
from app.core.config import settings

_LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def build_message(platform, case, unit, *, reports_summary: list[str], photo_urls: list[str]) -> dict:
    base = settings.WEB_PUBLIC_BASE_URL.rstrip("/")
    text = (
        f"【出勤通報】{platform.name}\n"
        f"案號 {case.case_number}｜{case.title}\n"
        f"嚴重度：{case.severity}｜回報 {case.unique_reporter_count} 人\n"
        f"位置：{case.location_label or case.town or ''}（{case.lat:.5f}, {case.lon:.5f}）\n"
        + (f"最新：{case.public_summary}\n" if case.public_summary else "")
        + ("".join(f"・{s}\n" for s in reports_summary[:3]))
        + f"案件：{base}/console/platforms/{case.platform_id}/cases/{case.id}"
    )
    return {
        "text": text,
        "payload": {
            "platform_id": str(platform.id),
            "platform": platform.name,
            "case_id": str(case.id),
            "case_number": case.case_number,
            "title": case.title,
            "category": case.category,
            "severity": case.severity,
            "status": case.status,
            "lat": case.lat,
            "lon": case.lon,
            "town": case.town,
            "location_label": case.location_label,
            "unique_reporters": case.unique_reporter_count,
            "report_count": case.report_count,
            "public_summary": case.public_summary,
            "reports": reports_summary[:5],
            "photos": [f"{settings.WEB_PUBLIC_BASE_URL.rstrip('/')}{u}" for u in photo_urls[:5]],
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "unit_kind": unit.kind,
            "console_url": f"{base}/console/platforms/{case.platform_id}/cases/{case.id}",
        },
    }


def send(message: dict, unit) -> dict:
    """Returns {channel, status, detail, external_ref}. Raises ConnectorError
    only when a *configured* real channel fails."""
    line_to = getattr(unit, "line_to", None)
    if settings.LINE_CHANNEL_ACCESS_TOKEN and line_to:
        resp = httpx.post(
            _LINE_PUSH_URL,
            headers={"Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json={"to": line_to, "messages": [{"type": "text", "text": message["text"]}]},
            timeout=15,
        )
        if resp.status_code >= 400:
            raise ConnectorError(f"LINE push {resp.status_code}: {resp.text[:200]}")
        return {"channel": "line", "status": "sent", "detail": f"已推播至 {unit.name} 的 LINE", "external_ref": resp.headers.get("x-line-request-id")}
    if settings.DISPATCH_WEBHOOK_URL:
        resp = httpx.post(settings.DISPATCH_WEBHOOK_URL, json=message["payload"], timeout=15)
        if resp.status_code >= 400:
            raise ConnectorError(f"webhook {resp.status_code}: {resp.text[:200]}")
        return {"channel": "webhook", "status": "sent", "detail": f"已送至出勤系統 webhook（HTTP {resp.status_code}）", "external_ref": None}
    return {"channel": "simulated", "status": "simulated", "detail": "未設定 LINE／webhook，出勤通報已記錄於稽核軌跡（模擬）", "external_ref": None}
