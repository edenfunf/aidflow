"""Incident case lifecycle (modules: incident_case_creation, case_review,
case_status, emic_report, community_handling, public_timeline).

Every change goes through ``transition`` (or a function built on it) so the
state machine is enforced, a CaseEvent row is written (public timeline) and
the outbox receives an audit event in the same transaction.

Notifications are *not* sent from here — callers commit first and then call
``after_commit`` so nobody is told about a change that rolled back.
"""
from __future__ import annotations

import logging

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors import emic
from app.connectors.base import ConnectorError
from app.core.config import settings
from app.db.models import CaseEvent, IncidentCase, Platform, Report, ReportCluster, ReportPhoto
from app.domain.case_states import (
    COMMUNITY_STATUSES,
    DONE_STATUSES,
    EMIC_STATUSES,
    PENDING_STATUSES,
    QUEUED_STATUSES,
    CaseStatus,
    assert_transition,
    public_label,
    track_of,
)
from app.domain.categories import category_label, severity_rank
from app.services import notification_service, outbox_service, privacy_service

logger = logging.getLogger("aidflow.cases")


class CaseNotFoundError(Exception):
    pass


class CaseActionError(Exception):
    """The action does not apply to the case in its current state."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# case numbers carry the local (Taiwan, UTC+8, no DST) date an officer would say
_TAIWAN = timezone(timedelta(hours=8))


def _prefix(platform: Platform) -> str:
    cfg = platform.configuration or {}
    if cfg.get("case_prefix"):
        return str(cfg["case_prefix"]).upper()[:6]
    letters = "".join(ch for ch in platform.slug.upper() if ch.isascii() and ch.isalnum())
    return (letters[:3] or "AF")


def next_case_number(db: Session, platform: Platform, at: datetime | None = None, offset: int = 0) -> str:
    at = at or _now()
    n = db.scalar(
        select(func.count()).select_from(IncidentCase).where(IncidentCase.platform_id == platform.id)
    ) or 0
    return f"{_prefix(platform)}-{at.astimezone(_TAIWAN):%Y%m%d}-{int(n) + 1 + offset:04d}"


def _insert_case(db: Session, platform: Platform, case: IncidentCase, at: datetime) -> None:
    """Insert with a savepoint; on a concurrent number collision take the
    next sequence number (bounded retries)."""
    for attempt in range(5):
        case.case_number = next_case_number(db, platform, at, offset=attempt)
        try:
            with db.begin_nested():
                db.add(case)
                db.flush()
            return
        except IntegrityError:
            continue
    raise RuntimeError("Could not allocate a unique case number")


def _event(
    db: Session,
    case: IncidentCase,
    *,
    event_type: str,
    actor_role: str = "system",
    actor_name: str | None = None,
    note: str | None = None,
    public: bool = True,
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict | None = None,
    at: datetime | None = None,
) -> CaseEvent:
    ev = CaseEvent(
        case_id=case.id,
        platform_id=case.platform_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_role=actor_role,
        actor_name=actor_name,
        note=note,
        public=public,
        payload=payload or {},
    )
    if at is not None:
        ev.created_at = at
    db.add(ev)
    db.flush()
    outbox_service.enqueue_event(
        db,
        event_type=f"case.{event_type}" if not event_type.startswith("case.") else event_type,
        aggregate_id=case.id,
        payload={
            "platform_id": str(case.platform_id),
            "case_id": str(case.id),
            "case_number": case.case_number,
            "title": case.title,
            "from_status": from_status,
            "to_status": to_status,
            "actor_role": actor_role,
            "actor_name": actor_name,
            "public": public,
            **(payload or {}),
        },
    )
    return ev


def _location_label(reports: list[Report], town: str | None) -> str:
    labels = [privacy_service.mask_address(r.address) for r in reports]
    labels = [l for l in labels if l]
    if labels:
        return Counter(labels).most_common(1)[0][0]
    return f"{town}一帶" if town else "位置待確認"


# ── creation ──────────────────────────────────────────────────────────────
def create_case_from_cluster(
    db: Session,
    platform: Platform,
    cluster: ReportCluster,
    *,
    trigger: str = "threshold",
    policy=None,
    actor_name: str | None = None,
) -> IncidentCase:
    """Promote a cluster to a case awaiting review. ``trigger`` is 'threshold'
    (N distinct reporters agreed) or 'manual' (人工成案 — an officer judged a
    report below the threshold credible). Either way the case waits for the
    審核點; nothing enters the queue unreviewed."""
    reports = list(
        db.scalars(
            select(Report).where(Report.cluster_id == cluster.id, Report.status != "rejected")
            .order_by(Report.created_at.asc())
        ).all()
    )
    last_at = reports[-1].created_at if reports else _now()
    town = cluster.town or next((r.town for r in reports if r.town), None)
    title = f"{town or ''}{category_label(cluster.category)}"

    case = IncidentCase(
        platform_id=platform.id,
        cluster_id=cluster.id,
        case_number="",
        title=title,
        category=cluster.category,
        severity=cluster.severity,
        status=CaseStatus.pending_review.value,
        lat=cluster.centroid_lat,
        lon=cluster.centroid_lon,
        town=town,
        location_label=_location_label(reports, town),
        report_count=cluster.report_count,
        unique_reporter_count=cluster.unique_reporter_count,
        threshold_reached_at=last_at if trigger == "threshold" else None,
    )
    created_at = last_at if trigger == "threshold" else _now()
    case.created_at = created_at
    _insert_case(db, platform, case, created_at)

    cluster.case_id = case.id
    cluster.status = "promoted"
    for idx, r in enumerate(reports, start=1):
        r.case_id = case.id
        r.status = "promoted"
        _link_photos(db, r, case)
        _event(
            db, case, event_type="report.received", actor_role="citizen",
            note=f"第 {idx} 筆民眾回報", at=r.created_at,
            payload={"report_id": str(r.id), "reporter_role": r.reporter_role, "category": r.category},
        )
    if trigger == "threshold":
        required = getattr(policy, "required_unique_reporters", None)
        _event(
            db, case, event_type="threshold_reached",
            note=f"同地點 {cluster.unique_reporter_count} 位不同民眾回報"
                 + (f"（門檻 {required} 人）" if required else ""),
            at=last_at + timedelta(milliseconds=1),
            payload={"unique_reporters": cluster.unique_reporter_count},
        )
        _event(
            db, case, event_type="case.created", to_status=CaseStatus.pending_review.value,
            note="成案，等待承辦人員審核處理方式", at=last_at + timedelta(milliseconds=2),
            payload={"trigger": trigger},
        )
    else:
        _event(
            db, case, event_type="case.created", to_status=CaseStatus.pending_review.value,
            actor_role="operator", actor_name=actor_name, note="承辦人員人工成案，等待審核", at=created_at,
            payload={"trigger": trigger},
        )
    db.flush()
    return case


def _link_photos(db: Session, report: Report, case: IncidentCase) -> None:
    """Photos attached to a report before it became (part of) a case belong
    to the case too."""
    db.execute(
        update(ReportPhoto)
        .where(ReportPhoto.report_id == report.id, ReportPhoto.case_id.is_(None))
        .values(case_id=case.id)
    )


def attach_report_to_case(db: Session, case: IncidentCase, report: Report, cluster: ReportCluster) -> None:
    report.case_id = case.id
    report.status = "promoted"
    _link_photos(db, report, case)
    case.report_count = cluster.report_count
    case.unique_reporter_count = cluster.unique_reporter_count
    if severity_rank(report.triage_severity) > severity_rank(case.severity):
        case.severity = report.triage_severity
    _event(
        db, case, event_type="report.received", actor_role="citizen",
        note=f"第 {case.report_count} 筆民眾回報", at=report.created_at,
        payload={"report_id": str(report.id), "reporter_role": report.reporter_role, "category": report.category},
    )


def promote_cluster(
    db: Session, platform: Platform, cluster: ReportCluster, *, actor_name: str | None
) -> IncidentCase:
    if cluster.case_id is not None:
        case = db.get(IncidentCase, cluster.case_id)
        if case is not None:
            return case
    return create_case_from_cluster(db, platform, cluster, trigger="manual", actor_name=actor_name)


# ── state changes ─────────────────────────────────────────────────────────
def transition(
    db: Session,
    case: IncidentCase,
    to_status: str,
    *,
    actor_role: str = "operator",
    actor_name: str | None = None,
    note: str | None = None,
    public: bool = True,
    at: datetime | None = None,
    payload: dict | None = None,
) -> CaseEvent:
    """Validated status change. Raises InvalidTransitionError."""
    assert_transition(case.status, to_status)
    frm = case.status
    case.status = to_status
    stamp = at or _now()
    track = track_of(to_status)
    if track:
        case.track = track
    if frm == CaseStatus.pending_review.value:
        case.reviewed_at = stamp
        case.reviewed_by = actor_name
    if to_status == CaseStatus.reported_emic.value and case.emic_reported_at is None:
        case.emic_reported_at = stamp
    if to_status == CaseStatus.community_submitted.value:
        case.community_submitted_at = stamp
    if to_status == CaseStatus.closed.value:
        case.closed_at = stamp
        case.resolved_at = case.resolved_at or stamp
    if to_status in (CaseStatus.closed.value, CaseStatus.dismissed.value) and case.cluster_id:
        cluster = db.get(ReportCluster, case.cluster_id)
        if cluster is not None:
            cluster.status = "closed" if to_status == CaseStatus.closed.value else "dismissed"
    return _event(
        db, case, event_type="status_changed", actor_role=actor_role, actor_name=actor_name,
        note=note or public_label(to_status), public=public, from_status=frm, to_status=to_status,
        at=at, payload=payload,
    )


def review(
    db: Session,
    platform: Platform,
    case: IncidentCase,
    decision: str,
    *,
    actor_name: str | None,
    note: str | None = None,
    at: datetime | None = None,
) -> dict:
    """審核點: decide how a pending case is handled.

    emic       → 上報 EMIC（see ``report_to_emic``）
    community  → 開放民眾協助處理
    dismiss    → 不成案
    """
    if case.status != CaseStatus.pending_review.value:
        raise CaseActionError("此案件已審核過")
    if decision == "emic":
        return report_to_emic(db, platform, case, actor_name=actor_name, note=note, at=at)
    if decision == "community":
        transition(db, case, CaseStatus.community_open.value, actor_name=actor_name, at=at,
                   note=note or "經審核為小型災情，開放民眾協助處理；處理完成請上傳照片回報")
        return {"decision": decision}
    if decision == "dismiss":
        transition(db, case, CaseStatus.dismissed.value, actor_name=actor_name, at=at,
                   note=note or "經審核判定不成案（誤報或重複）")
        return {"decision": decision}
    raise CaseActionError("未知的審核決定")


def report_to_emic(
    db: Session,
    platform: Platform,
    case: IncidentCase,
    *,
    actor_name: str | None,
    note: str | None = None,
    at: datetime | None = None,
) -> dict:
    """Move the case to 已上報 EMIC. With EMIC_SUBMIT_URL configured the case
    is sent; otherwise (or when sending fails) the officer files it in EMIC by
    hand and records the EMIC case number — the result says which."""
    transition(db, case, CaseStatus.reported_emic.value, actor_name=actor_name, at=at,
               note=note or "經審核需上報，已列入 EMIC 上報")
    result = {"decision": "emic", "mode": emic.mode(), "submitted": False, "detail": None}
    case.emic_channel = "manual"
    if emic.mode() == "api":
        reports = reports_of(db, case.id)
        from app.services import media_service

        base = settings.API_PUBLIC_BASE_URL.rstrip("/")
        photos = [f"{base}{media_service.public_url(p)}" for p in media_service.photos_for_case(db, case.id, public_only=True)]
        try:
            got = emic.submit(emic.build_payload(platform, case, reports, photos))
            case.emic_channel = "api"
            case.emic_case_no = got.get("case_no") or case.emic_case_no
            case.emic_status = got.get("status") or case.emic_status
            case.emic_synced_at = _now()
            result.update(submitted=True, detail="已送出至 EMIC 介接端點")
            _event(db, case, event_type="emic_submitted", actor_role="system", public=False,
                   note="已透過介接端點上報 EMIC" + (f"（EMIC 案號 {case.emic_case_no}）" if case.emic_case_no else ""),
                   payload={"emic_case_no": case.emic_case_no})
        except ConnectorError as exc:
            result.update(detail=f"自動上報失敗，請改以人工登錄：{exc.reason}")
            _event(db, case, event_type="emic_submit_failed", actor_role="system", public=False,
                   note=f"EMIC 自動上報失敗：{exc.reason}")
    else:
        result["detail"] = "EMIC 介接規格尚未提供：請於 EMIC 建立案件後，回填 EMIC 案號與處理狀態。"
    return result


def update_emic(
    db: Session,
    case: IncidentCase,
    *,
    actor_name: str | None,
    emic_case_no: str | None = None,
    emic_status: str | None = None,
    assigned_unit: str | None = None,
    note: str | None = None,
    to_status: str | None = None,
    at: datetime | None = None,
) -> CaseEvent | None:
    """Record what EMIC says about the case (manual entry or a sync), and
    optionally move it to 處理中 / 已結案."""
    if case.status not in {s.value for s in EMIC_STATUSES}:
        raise CaseActionError("只有已上報 EMIC 的案件可以更新 EMIC 資訊")
    changes: dict = {}
    if emic_case_no is not None and emic_case_no.strip() != (case.emic_case_no or ""):
        case.emic_case_no = emic_case_no.strip() or None
        changes["emic_case_no"] = case.emic_case_no
    if emic_status is not None and emic_status.strip() != (case.emic_status or ""):
        case.emic_status = emic_status.strip() or None
        changes["emic_status"] = case.emic_status
    if assigned_unit is not None and assigned_unit.strip() != (case.assigned_unit or ""):
        case.assigned_unit = assigned_unit.strip() or None
        changes["assigned_unit"] = case.assigned_unit
    ev = None
    if changes:
        case.emic_synced_at = at or _now()
        parts = []
        if "emic_status" in changes and case.emic_status:
            parts.append(f"EMIC 處理狀態：{case.emic_status}")
        if "assigned_unit" in changes and case.assigned_unit:
            parts.append(f"處理單位：{case.assigned_unit}")
        # the EMIC case number itself is internal
        public_parts = parts[:]
        if "emic_case_no" in changes and case.emic_case_no:
            parts.append(f"EMIC 案號 {case.emic_case_no}")
        ev = _event(
            db, case, event_type="emic_updated", actor_name=actor_name,
            note="；".join(public_parts) or "已登錄 EMIC 案號", public=bool(public_parts), at=at,
            payload={"changes": changes, "internal_note": "；".join(parts)},
        )
    if note:
        add_update(db, case, note=note, public=True, actor_name=actor_name, at=at)
    if to_status:
        ev = transition(db, case, to_status, actor_name=actor_name, at=at)
    return ev


def community_submit(
    db: Session,
    case: IncidentCase,
    *,
    note: str | None,
    helper_name: str | None = None,
    photo_count: int = 0,
    at: datetime | None = None,
) -> CaseEvent:
    """A citizen reports a 民間可處理 case as handled (photos already saved)."""
    if case.status != CaseStatus.community_open.value:
        raise CaseActionError("此案件目前不開放民眾回報處理")
    clean = privacy_service.redact_text((note or "").strip()) or None
    return transition(
        db, case, CaseStatus.community_submitted.value, actor_role="citizen", actor_name=None, at=at,
        note="民眾回報已處理完成，等待承辦人員確認" + (f"：{clean}" if clean else ""),
        payload={"photo_count": photo_count, "helper_named": bool(helper_name)},
    )


def community_confirm(
    db: Session,
    case: IncidentCase,
    *,
    approve: bool,
    actor_name: str | None,
    note: str | None = None,
    at: datetime | None = None,
) -> CaseEvent:
    if case.status != CaseStatus.community_submitted.value:
        raise CaseActionError("此案件沒有待確認的民眾處理回報")
    if approve:
        return transition(db, case, CaseStatus.closed.value, actor_name=actor_name, at=at,
                          note=note or "承辦人員確認處理完成，結案並自地圖撤除")
    return transition(db, case, CaseStatus.community_open.value, actor_name=actor_name, at=at,
                      note="處理照片未通過確認，重新開放民眾協助" + (f"：{note}" if note else ""))


def add_update(
    db: Session,
    case: IncidentCase,
    *,
    note: str,
    public: bool = True,
    actor_name: str | None = None,
    at: datetime | None = None,
) -> CaseEvent:
    """A progress note; public ones appear on the citizen timeline."""
    if public:
        case.public_summary = note
    return _event(
        db, case, event_type="public_update" if public else "internal_note",
        actor_role="operator", actor_name=actor_name, note=note, public=public, at=at,
    )


def after_commit(db: Session, platform: Platform, case: IncidentCase, *, previous_status: str | None) -> None:
    """Tell the right people about a committed change (never raises)."""
    if case.status == previous_status:
        return
    try:
        if case.status == CaseStatus.pending_review.value:
            notification_service.staff_review_needed(platform, case)
        elif case.status == CaseStatus.community_submitted.value:
            notification_service.staff_community_submitted(platform, case)
        notification_service.notify_reporters(db, platform, case)
    except Exception as exc:  # noqa: BLE001 — a notification must never fail the request
        logger.warning("case notification failed for %s: %s", case.id, exc)


# ── queries ───────────────────────────────────────────────────────────────
def get_case(db: Session, case_id: uuid.UUID) -> IncidentCase | None:
    return db.get(IncidentCase, case_id)


def require_case(db: Session, case_id: uuid.UUID) -> IncidentCase:
    case = db.get(IncidentCase, case_id)
    if case is None:
        raise CaseNotFoundError()
    return case


_PHASES: dict[str, frozenset[CaseStatus]] = {
    "pending": PENDING_STATUSES,
    "active": EMIC_STATUSES,
    "community": COMMUNITY_STATUSES,
    "queued": QUEUED_STATUSES,
    "done": DONE_STATUSES,
}


def list_cases(
    db: Session,
    platform_id: uuid.UUID,
    *,
    statuses: list[str] | None = None,
    phase: str | None = None,
    track: str | None = None,
    category: str | None = None,
    town: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    public_only: bool = False,
    sort: str = "created_desc",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[IncidentCase], int]:
    filters = [IncidentCase.platform_id == platform_id]
    if statuses:
        filters.append(IncidentCase.status.in_(statuses))
    if phase in _PHASES:
        filters.append(IncidentCase.status.in_([s.value for s in _PHASES[phase]]))
    elif phase == "open":
        filters.append(IncidentCase.status.not_in([CaseStatus.closed.value, CaseStatus.dismissed.value]))
    if track:
        filters.append(IncidentCase.track == track)
    if public_only:
        filters.append(IncidentCase.status != CaseStatus.dismissed.value)
    if category:
        filters.append(IncidentCase.category == category)
    if town:
        filters.append(IncidentCase.town == town)
    if severity:
        filters.append(IncidentCase.severity == severity)
    if since is not None:
        filters.append(IncidentCase.created_at >= since)

    total = db.scalar(select(func.count()).select_from(IncidentCase).where(*filters)) or 0
    q = select(IncidentCase).where(*filters)
    if sort == "severity_desc":
        rows = list(db.scalars(q).all())
        rows.sort(key=lambda c: (-severity_rank(c.severity), -(c.created_at.timestamp() if c.created_at else 0)))
        return rows[offset:offset + limit], int(total)
    if sort == "reports_desc":
        q = q.order_by(IncidentCase.unique_reporter_count.desc(), IncidentCase.created_at.desc())
    elif sort == "created_asc":
        q = q.order_by(IncidentCase.created_at.asc())
    elif sort == "updated_desc":
        q = q.order_by(IncidentCase.updated_at.desc())
    else:
        q = q.order_by(IncidentCase.created_at.desc())
    rows = list(db.scalars(q.limit(limit).offset(offset)).all())
    return rows, int(total)


def timeline(db: Session, case_id: uuid.UUID, *, public_only: bool) -> list[CaseEvent]:
    q = select(CaseEvent).where(CaseEvent.case_id == case_id)
    if public_only:
        q = q.where(CaseEvent.public.is_(True))
    return list(db.scalars(q.order_by(CaseEvent.created_at.asc(), CaseEvent.id.asc())).all())


def reports_of(db: Session, case_id: uuid.UUID) -> list[Report]:
    return list(
        db.scalars(select(Report).where(Report.case_id == case_id).order_by(Report.created_at.asc())).all()
    )


def nearby_cases(
    db: Session, case: IncidentCase, *, radius_m: float = 2000, limit: int = 6
) -> list[tuple[IncidentCase, float]]:
    from app.utils.geo import bbox_for, haversine_m

    min_lat, min_lon, max_lat, max_lon = bbox_for(case.lat, case.lon, radius_m)
    rows = db.scalars(
        select(IncidentCase).where(
            IncidentCase.platform_id == case.platform_id,
            IncidentCase.id != case.id,
            IncidentCase.lat.between(min_lat, max_lat),
            IncidentCase.lon.between(min_lon, max_lon),
        )
    ).all()
    out = []
    for c in rows:
        d = haversine_m(case.lat, case.lon, c.lat, c.lon)
        if d <= radius_m:
            out.append((c, d))
    out.sort(key=lambda t: t[1])
    return out[:limit]
