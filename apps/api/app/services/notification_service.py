"""Outbound notifications (module: line_notify).

Fires on case milestones. With a LINE channel token configured the message is
really broadcast; otherwise the intent is recorded to the outbox as a
simulated notification so the audit trail still shows what *would* have gone
out. Never raises — a notification failure must not roll back a case change.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.connectors import line
from app.connectors.base import ConnectorError
from app.core.config import settings
from app.domain.case_states import public_label
from app.domain.categories import category_label
from app.services import outbox_service

_MILESTONES = {"created", "assigned", "on_site", "resolved", "closed"}


def _message(platform, case, milestone: str) -> str:
    label = "正式成案" if milestone == "created" else public_label(milestone)
    url = f"{settings.WEB_PUBLIC_BASE_URL.rstrip('/')}/p/{platform.slug}/cases/{case.id}"
    return (
        f"【{platform.name}】{case.title}（{category_label(case.category)}）{label}\n"
        f"案號 {case.case_number}・{case.unique_reporter_count} 人回報\n"
        f"處理進度：{url}"
    )


def notify_case(db: Session, platform, case, milestone: str) -> None:
    if platform is None or milestone not in _MILESTONES:
        return
    if "line_notify" not in (platform.modules or []):
        return
    text = _message(platform, case, milestone)
    payload = {
        "platform_id": str(platform.id),
        "case_id": str(case.id),
        "milestone": milestone,
        "channel": "line",
    }
    if not line.is_configured():
        outbox_service.enqueue_event(
            db, event_type="notification.simulated", aggregate_id=case.id,
            payload={**payload, "text": text, "reason": "LINE_CHANNEL_ACCESS_TOKEN not set"},
        )
        return
    try:
        result = line.broadcast(text=text)
        outbox_service.enqueue_event(
            db, event_type="notification.sent", aggregate_id=case.id,
            payload={**payload, "external_ref": result.get("external_ref")},
        )
    except ConnectorError as exc:
        outbox_service.enqueue_event(
            db, event_type="notification.failed", aggregate_id=case.id,
            payload={**payload, "reason": exc.reason},
        )
