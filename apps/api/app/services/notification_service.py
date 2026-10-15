"""Outbound notifications (G-09 LINE BOT 群組通知, P-05 / S-07 進度通知).

Two audiences:

  staff     — the county LINE group bound to the platform receives a push when
              a new incident spot is reported, when a case needs review, and
              when a citizen reports a small case as handled.
  reporters — citizens who ticked 「接收案件進度」 and left an e-mail get a
              message each time their case changes status.

Rules: call these only *after* the business transaction has committed; they
never raise. Every attempt is written to ``notification_logs`` (recipient
masked). Unconfigured channels are logged as ``simulated`` — nothing is sent
and nothing pretends it was. Real sends run on a short-lived worker thread so a
slow SMTP server cannot hold up the citizen's request.
"""
from __future__ import annotations

import logging
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import line, mailer
from app.connectors.base import ConnectorError
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import IncidentCase, NotificationLog, Platform, Report, ReportCluster
from app.domain.case_states import public_label
from app.domain.categories import category_label

logger = logging.getLogger("aidflow.notify")

_SEVERITY = {"critical": "極高", "high": "高", "medium": "中", "low": "低"}
# statuses a subscribed reporter hears about
_REPORTER_MILESTONES = {"pending_review", "reported_emic", "emic_processing", "community_open",
                        "community_submitted", "closed", "dismissed"}


def mask_email(addr: str | None) -> str | None:
    if not addr or "@" not in addr:
        return None
    local, domain = addr.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _web() -> str:
    return settings.WEB_PUBLIC_BASE_URL.rstrip("/")


def _log(job: dict, status: str, detail: str | None) -> None:
    try:
        with SessionLocal() as s:
            s.add(NotificationLog(
                platform_id=job.get("platform_id"), case_id=job.get("case_id"), report_id=job.get("report_id"),
                channel=job["channel"], kind=job["kind"], recipient=job.get("masked"), status=status,
                detail=(detail or "")[:500] or None,
            ))
            s.commit()
    except Exception as exc:  # noqa: BLE001 — logging must never break the caller
        logger.warning("notification log failed: %s", exc)


def _send(job: dict) -> None:
    try:
        if job["channel"] == "line":
            ref = line.push_text(job["to"], job["text"])
            _log(job, "sent", f"LINE request id {ref}" if ref else None)
        else:
            mailer.send(job["to"], job["subject"], job["text"])
            _log(job, "sent", None)
    except ConnectorError as exc:
        _log(job, "failed", exc.reason if hasattr(exc, "reason") else str(exc))
    except Exception as exc:  # noqa: BLE001
        _log(job, "failed", str(exc))


def _deliver(job: dict) -> str:
    configured = line.is_configured() if job["channel"] == "line" else mailer.is_configured()
    if not job.get("to"):
        _log(job, "skipped", job.get("skip_reason") or "沒有收件對象")
        return "skipped"
    if not configured:
        why = "LINE_CHANNEL_ACCESS_TOKEN 未設定" if job["channel"] == "line" else "SMTP_HOST 未設定"
        _log(job, "simulated", f"{why}；未實際送出")
        return "simulated"
    threading.Thread(target=_send, args=(job,), daemon=True, name=f"notify-{job['kind']}").start()
    return "queued"


# ── staff (LINE group) ────────────────────────────────────────────────────
def line_group_for(platform: Platform) -> str | None:
    return (platform.configuration or {}).get("line_group_id") or None


def _staff(platform: Platform, kind: str, text: str, *, case_id=None, report_id=None) -> str:
    group = line_group_for(platform)
    return _deliver({
        "channel": "line", "kind": kind, "to": group, "masked": f"群組 {group[:8]}…" if group else None,
        "text": text, "platform_id": platform.id, "case_id": case_id, "report_id": report_id,
        "skip_reason": "此平台尚未綁定 LINE 群組",
    })


def staff_new_report(platform: Platform, report: Report, cluster: ReportCluster | None) -> str:
    """A report that opened a new spot (or carries no location) — the group
    should know something new came in. Reports joining an existing spot do not
    push again; the review message covers them."""
    where = report.town or "位置未提供"
    lines = [
        f"【新災情通報】{platform.name}",
        f"{category_label(report.category)}｜{where}｜嚴重度 {_SEVERITY.get(report.triage_severity, report.triage_severity)}",
    ]
    if report.description:
        from app.services.privacy_service import redact_text

        lines.append(f"描述：{(redact_text(report.description) or '')[:80]}")
    if cluster is not None:
        lines.append(f"同地點目前 {cluster.unique_reporter_count} 位回報者")
    lines.append(f"請至政府管理後台查看：{_web()}/console/platforms/{platform.id}")
    return _staff(platform, "new_report", "\n".join(lines), report_id=report.id)


def staff_review_needed(platform: Platform, case: IncidentCase) -> str:
    text = (
        f"【待審核】{platform.name}\n"
        f"{case.case_number}｜{case.title}｜嚴重度 {_SEVERITY.get(case.severity, case.severity)}\n"
        f"{case.unique_reporter_count} 位民眾回報，請判斷：上報 EMIC／民間可處理／不成案\n"
        f"審核：{_web()}/console/platforms/{platform.id}/cases/{case.id}"
    )
    return _staff(platform, "review_needed", text, case_id=case.id)


def staff_community_submitted(platform: Platform, case: IncidentCase) -> str:
    text = (
        f"【民眾回報已處理】{platform.name}\n"
        f"{case.case_number}｜{case.title}\n"
        f"民眾已上傳處理完成照片，請確認後結案。\n"
        f"確認：{_web()}/console/platforms/{platform.id}/cases/{case.id}"
    )
    return _staff(platform, "community_submitted", text, case_id=case.id)


def staff_test(platform: Platform, actor: str) -> str:
    text = f"【測試訊息】{platform.name}\nLINE 群組通知設定完成（由 {actor} 發送）。"
    return _staff(platform, "test", text)


# ── reporters (e-mail) ────────────────────────────────────────────────────
def _reporter_message(platform: Platform, case: IncidentCase, report: Report) -> tuple[str, str]:
    label = public_label(case.status)
    subject = f"【{platform.name}】您通報的災情：{label}"
    detail = {
        "pending_review": "您的通報已成案，承辦人員正在審核處理方式。",
        "reported_emic": "承辦人員已將此災情上報內政部消防署 EMIC 系統，由權責單位處理。",
        "emic_processing": "權責單位正在處理此災情。" + (f"（EMIC 狀態：{case.emic_status}）" if case.emic_status else ""),
        "community_open": "此災情經審核為小型災情，已開放民眾協助處理；若您已處理完成，可於案件頁上傳照片回報。",
        "community_submitted": "已有民眾回報處理完成，等待承辦人員確認。",
        "closed": "此災情已處理完成並結案，感謝您的通報。",
        "dismissed": "此通報經承辦人員審核，判定為重複或不需處理的通報。",
    }.get(case.status, label)
    lines = [
        f"您好：",
        "",
        f"您於 {report.created_at:%Y/%m/%d %H:%M} 通報的「{category_label(report.category)}」（案號 {case.case_number}）",
        f"目前狀態：{label}",
        detail,
    ]
    if case.public_summary:
        lines.append(f"最新進度：{case.public_summary}")
    if case.status != "dismissed":
        lines += ["", f"查看處理進度：{_web()}/p/{platform.slug}/cases/{case.id}"]
    lines += [
        "",
        "—",
        "本信件由系統自動發送，請勿直接回覆。危及生命請撥打 119。",
        f"不想再收到此案件通知：{_web()}/unsubscribe?token={report.notify_token}",
    ]
    return subject, "\n".join(lines)


def notify_reporter(platform: Platform, case: IncidentCase, report: Report) -> str:
    """One subscriber — e.g. a report that just joined an existing case."""
    email = (report.reporter_email or "").strip().lower()
    if not report.notify_opt_in or not email:
        return "skipped"
    subject, body = _reporter_message(platform, case, report)
    return _deliver({"channel": "email", "kind": "case_progress", "to": email, "masked": mask_email(email),
                     "subject": subject, "text": body, "platform_id": platform.id, "case_id": case.id,
                     "report_id": report.id})


def notify_reporters(db: Session, platform: Platform, case: IncidentCase) -> int:
    """E-mail every subscribed reporter of ``case`` about its current status.
    Returns how many were attempted."""
    if case.status not in _REPORTER_MILESTONES:
        return 0
    reports = db.scalars(
        select(Report).where(Report.case_id == case.id, Report.notify_opt_in.is_(True), Report.status != "rejected")
    ).all()
    seen: set[str] = set()
    n = 0
    for r in reports:
        email = (r.reporter_email or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        subject, body = _reporter_message(platform, case, r)
        _deliver({"channel": "email", "kind": "case_progress", "to": email, "masked": mask_email(email),
                  "subject": subject, "text": body, "platform_id": platform.id, "case_id": case.id,
                  "report_id": r.id})
        n += 1
    return n


def unsubscribe(db: Session, token: str) -> Report | None:
    if not token:
        return None
    report = db.scalar(select(Report).where(Report.notify_token == token))
    if report is None:
        return None
    report.notify_opt_in = False
    db.commit()
    return report


def recent_logs(db: Session, platform_id: uuid.UUID, limit: int = 50) -> list[NotificationLog]:
    return list(db.scalars(
        select(NotificationLog).where(NotificationLog.platform_id == platform_id)
        .order_by(NotificationLog.created_at.desc()).limit(limit)
    ).all())
