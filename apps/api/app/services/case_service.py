"""Incident case lifecycle (modules: incident_case_creation, case_status,
case_dispatch, case_assignment, public_timeline).

Every change goes through ``transition``/``assign``/``add_update`` so that the
state machine is enforced, a CaseEvent row is written (public timeline) and
the outbox receives an audit event in the same transaction.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CaseAssignment, CaseEvent, IncidentCase, Platform, Report, ReportCluster, ReportPhoto
from app.domain.case_states import (
    ACTIVE_STATUSES,
    DONE_STATUSES,
    PENDING_STATUSES,
    CaseStatus,
    assert_transition,
    public_label,
)
from app.domain.categories import category_label, severity_rank
from app.services import notification_service, outbox_service, privacy_service


class CaseNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    return f"{_prefix(platform)}-{at:%Y%m%d}-{int(n) + 1 + offset:04d}"


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
            "from_status": from_status,
            "to_status": to_status,
            "actor_role": actor_role,
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


def create_case_from_cluster(
    db: Session,
    platform: Platform,
    cluster: ReportCluster,
    *,
    trigger: str = "threshold",
    policy=None,
    actor_name: str | None = None,
) -> IncidentCase:
    """Promote a cluster. ``trigger`` is 'threshold' (automatic) or 'manual'
    (operator judged a single report credible). Automatic cases land in
    awaiting_dispatch; manual ones start in verifying."""
    reports = list(
        db.scalars(
            select(Report).where(Report.cluster_id == cluster.id, Report.status != "rejected")
            .order_by(Report.created_at.asc())
        ).all()
    )
    first_at = reports[0].created_at if reports else _now()
    last_at = reports[-1].created_at if reports else _now()
    town = cluster.town or next((r.town for r in reports if r.town), None)
    title = f"{town or ''}{category_label(cluster.category)}"
    initial = CaseStatus.awaiting_dispatch if trigger == "threshold" else CaseStatus.verifying

    case = IncidentCase(
        platform_id=platform.id,
        cluster_id=cluster.id,
        case_number="",
        title=title,
        category=cluster.category,
        severity=cluster.severity,
        status=initial.value,
        lat=cluster.centroid_lat,
        lon=cluster.centroid_lon,
        town=town,
        location_label=_location_label(reports, town),
        report_count=cluster.report_count,
        unique_reporter_count=cluster.unique_reporter_count,
        threshold_reached_at=last_at if trigger == "threshold" else None,
    )
    case.created_at = last_at
    _insert_case(db, platform, case, last_at)

    cluster.case_id = case.id
    cluster.status = "promoted"
    for idx, r in enumerate(reports, start=1):
        r.case_id = case.id
        r.status = "promoted"
        _link_photos(db, r, case)
        _event(
            db, case, event_type="report.received", actor_role="citizen",
            note=f"第 {idx} 筆民眾回報", at=r.created_at,
            payload={"report_id": str(r.id), "reporter_role": r.reporter_role,
                     "category": r.category},
        )
    if trigger == "threshold":
        required = getattr(policy, "required_unique_reporters", None)
        _event(
            db, case, event_type="threshold_reached", to_status=CaseStatus.threshold_reached.value,
            note=f"達到案件成立門檻（{cluster.unique_reporter_count} 位不同回報者"
                 + (f"，門檻 {required} 人）" if required else "）"),
            # strictly after the last report event that triggered it
            at=last_at + timedelta(milliseconds=1),
            payload={"unique_reporters": cluster.unique_reporter_count},
        )
        _event(
            db, case, event_type="case.created", from_status=CaseStatus.threshold_reached.value,
            to_status=CaseStatus.awaiting_dispatch.value, note="正式案件成立，等待派工",
            # strictly after the threshold event so the timeline order is deterministic
            at=last_at + timedelta(milliseconds=2),
            payload={"trigger": trigger, "case_number": case.case_number},
        )
    else:
        _event(
            db, case, event_type="case.created", to_status=initial.value, actor_role="operator",
            actor_name=actor_name, note="承辦人員建立案件，查證中", at=_now(),
            payload={"trigger": trigger, "case_number": case.case_number},
        )
    db.flush()
    notification_service.notify_case(db, platform, case, "created")
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
        payload={"report_id": str(report.id), "reporter_role": report.reporter_role,
                 "category": report.category},
    )


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
) -> CaseEvent:
    """Validated status change. Raises InvalidTransitionError."""
    assert_transition(case.status, to_status)
    frm = case.status
    case.status = to_status
    stamp = at or _now()
    if to_status == CaseStatus.assigned.value and case.dispatched_at is None:
        case.dispatched_at = stamp
    if to_status == CaseStatus.resolved.value:
        case.resolved_at = stamp
    if to_status == CaseStatus.closed.value:
        case.closed_at = stamp
    if to_status in (CaseStatus.closed.value, CaseStatus.dismissed.value) and case.cluster_id:
        cluster = db.get(ReportCluster, case.cluster_id)
        if cluster is not None:
            cluster.status = "closed" if to_status == CaseStatus.closed.value else "dismissed"
    if to_status == CaseStatus.awaiting_dispatch.value and frm in (
        CaseStatus.assigned.value, CaseStatus.en_route.value
    ):
        # dispatch cancelled — close the active assignment
        for a in db.scalars(
            select(CaseAssignment).where(CaseAssignment.case_id == case.id, CaseAssignment.status == "active")
        ).all():
            a.status = "cancelled"
        case.assigned_unit = None
    if to_status in DONE_STATUSES and to_status == CaseStatus.resolved.value:
        for a in db.scalars(
            select(CaseAssignment).where(CaseAssignment.case_id == case.id, CaseAssignment.status == "active")
        ).all():
            a.status = "completed"
    ev = _event(
        db, case, event_type="status_changed", actor_role=actor_role, actor_name=actor_name,
        note=note or public_label(to_status), public=public, from_status=frm, to_status=to_status,
        at=at,
    )
    notification_service.notify_case(db, db.get(Platform, case.platform_id), case, to_status)
    return ev


def assign(
    db: Session,
    case: IncidentCase,
    *,
    unit_name: str,
    team_lead: str | None = None,
    contact: str | None = None,
    note: str | None = None,
    actor_name: str | None = None,
    at: datetime | None = None,
) -> CaseAssignment:
    """縣府確認並派工: records the assignment and moves the case to assigned
    (from awaiting_dispatch / verifying / threshold_reached / reported)."""
    if case.status in (CaseStatus.reported.value, CaseStatus.verifying.value,
                       CaseStatus.threshold_reached.value):
        transition(db, case, CaseStatus.awaiting_dispatch.value, actor_role="operator",
                   actor_name=actor_name, note="縣府確認成案", at=at)
    assignment = CaseAssignment(
        case_id=case.id, platform_id=case.platform_id, unit_name=unit_name,
        team_lead=team_lead, contact=contact, note=note, status="active",
    )
    if at is not None:
        assignment.created_at = at
    db.add(assignment)
    case.assigned_unit = unit_name
    db.flush()
    if case.status == CaseStatus.awaiting_dispatch.value:
        transition(db, case, CaseStatus.assigned.value, actor_role="operator", actor_name=actor_name,
                   note=f"已派遣{unit_name}前往處理", at=at)
    else:
        _event(db, case, event_type="assignment_changed", actor_role="operator", actor_name=actor_name,
               note=f"改派{unit_name}", payload={"unit_name": unit_name}, at=at)
    return assignment


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


def get_case(db: Session, case_id: uuid.UUID) -> IncidentCase | None:
    return db.get(IncidentCase, case_id)


def require_case(db: Session, case_id: uuid.UUID) -> IncidentCase:
    case = db.get(IncidentCase, case_id)
    if case is None:
        raise CaseNotFoundError()
    return case


_SORTS = {
    "severity": lambda desc: (desc, "severity"),
}


def list_cases(
    db: Session,
    platform_id: uuid.UUID,
    *,
    statuses: list[str] | None = None,
    phase: str | None = None,
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
    if phase == "pending":
        filters.append(IncidentCase.status.in_([s.value for s in PENDING_STATUSES]))
    elif phase == "active":
        filters.append(IncidentCase.status.in_([s.value for s in ACTIVE_STATUSES]))
    elif phase == "done":
        filters.append(IncidentCase.status.in_([s.value for s in DONE_STATUSES]))
    elif phase == "open":
        filters.append(IncidentCase.status.not_in([CaseStatus.closed.value, CaseStatus.dismissed.value]))
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
    if sort == "reports_desc":
        q = q.order_by(IncidentCase.unique_reporter_count.desc(), IncidentCase.created_at.desc())
    elif sort == "created_asc":
        q = q.order_by(IncidentCase.created_at.asc())
    elif sort == "updated_desc":
        q = q.order_by(IncidentCase.updated_at.desc())
    else:
        q = q.order_by(IncidentCase.created_at.desc())
    rows = list(db.scalars(q.limit(limit).offset(offset)).all())
    if sort == "severity_desc":
        rows.sort(key=lambda c: (-severity_rank(c.severity), c.created_at), reverse=False)
    return rows, int(total)


def timeline(db: Session, case_id: uuid.UUID, *, public_only: bool) -> list[CaseEvent]:
    q = select(CaseEvent).where(CaseEvent.case_id == case_id)
    if public_only:
        q = q.where(CaseEvent.public.is_(True))
    return list(db.scalars(q.order_by(CaseEvent.created_at.asc(), CaseEvent.id.asc())).all())


def assignments(db: Session, case_id: uuid.UUID) -> list[CaseAssignment]:
    return list(
        db.scalars(
            select(CaseAssignment).where(CaseAssignment.case_id == case_id)
            .order_by(CaseAssignment.created_at.desc())
        ).all()
    )


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


def promote_cluster(
    db: Session, platform: Platform, cluster: ReportCluster, *, actor_name: str | None
) -> IncidentCase:
    if cluster.case_id is not None:
        case = db.get(IncidentCase, cluster.case_id)
        if case is not None:
            return case
    return create_case_from_cluster(db, platform, cluster, trigger="manual", actor_name=actor_name)
