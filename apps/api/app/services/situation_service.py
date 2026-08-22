"""Situational read-models (modules: incident_statistics, trend_visualization,
incident_map). Everything is computed from the live tables; the public
variants go through the privacy transformation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CaseEvent, IncidentCase, Platform, Report, ReportCluster
from app.domain.case_states import (
    ACTIVE_STATUSES,
    DONE_STATUSES,
    PENDING_STATUSES,
    CaseStatus,
    phase_of,
    public_label,
)
from app.domain.categories import REPORTER_ROLES, category_label, layer_for
from app.services import privacy_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _count(db: Session, model, *where) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _group(db: Session, column, *where) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).where(*where).group_by(column)).all()
    return {str(k): int(n) for k, n in rows if k is not None}


def _ordered(counts: dict[str, int], labeler, order: list[str] | None = None) -> list[dict]:
    keys = list(counts.keys())
    if order:
        keys.sort(key=lambda k: order.index(k) if k in order else len(order))
    else:
        keys.sort(key=lambda k: -counts[k])
    return [{"key": k, "label": labeler(k), "count": counts[k]} for k in keys]


def trend_buckets(db: Session, platform_id: uuid.UUID, *, hours: int = 24) -> list[dict]:
    now = _now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start = now - timedelta(hours=hours)
    buckets = {start + timedelta(hours=i): {"reports": 0, "cases_created": 0, "cases_resolved": 0} for i in range(hours)}

    def bucket_of(ts: datetime) -> datetime | None:
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        b = ts.replace(minute=0, second=0, microsecond=0)
        return b if b in buckets else None

    for (ts,) in db.execute(select(Report.created_at).where(Report.platform_id == platform_id, Report.created_at >= start)).all():
        b = bucket_of(ts)
        if b:
            buckets[b]["reports"] += 1
    for (ts,) in db.execute(select(IncidentCase.created_at).where(IncidentCase.platform_id == platform_id, IncidentCase.created_at >= start)).all():
        b = bucket_of(ts)
        if b:
            buckets[b]["cases_created"] += 1
    for (ts,) in db.execute(select(IncidentCase.resolved_at).where(IncidentCase.platform_id == platform_id, IncidentCase.resolved_at >= start)).all():
        b = bucket_of(ts)
        if b:
            buckets[b]["cases_resolved"] += 1
    return [{"start": k.isoformat(), **v} for k, v in sorted(buckets.items())]


def trend_direction(buckets: list[dict]) -> str:
    if len(buckets) < 6:
        return "steady"
    recent = sum(b["reports"] for b in buckets[-3:])
    previous = sum(b["reports"] for b in buckets[-6:-3])
    if recent >= previous * 1.3 and recent - previous >= 2:
        return "rising"
    if previous >= recent * 1.3 and previous - recent >= 2:
        return "falling"
    return "steady"


def situation(db: Session, platform: Platform) -> dict:
    pid = platform.id
    now = _now()
    status_counts = _group(db, IncidentCase.status, IncidentCase.platform_id == pid)
    pending = sum(status_counts.get(s.value, 0) for s in PENDING_STATUSES)
    active = sum(status_counts.get(s.value, 0) for s in ACTIVE_STATUSES)
    done = sum(status_counts.get(s.value, 0) for s in DONE_STATUSES)
    dismissed = status_counts.get(CaseStatus.dismissed.value, 0)
    total = sum(status_counts.values())
    high_risk = _count(
        db, IncidentCase, IncidentCase.platform_id == pid, IncidentCase.severity.in_(("high", "critical")),
        IncidentCase.status.not_in((CaseStatus.closed.value, CaseStatus.dismissed.value, CaseStatus.resolved.value)),
    )
    open_cases = total - done - dismissed
    cat_counts = _group(db, IncidentCase.category, IncidentCase.platform_id == pid,
                        IncidentCase.status != CaseStatus.dismissed.value)
    town_counts = _group(db, IncidentCase.town, IncidentCase.platform_id == pid,
                         IncidentCase.status != CaseStatus.dismissed.value)
    sev_counts = _group(db, IncidentCase.severity, IncidentCase.platform_id == pid,
                        IncidentCase.status.not_in((CaseStatus.closed.value, CaseStatus.dismissed.value)))
    last_report = db.scalar(select(func.max(Report.created_at)).where(Report.platform_id == pid))
    last_event = db.scalar(select(func.max(CaseEvent.created_at)).where(CaseEvent.platform_id == pid))
    buckets = trend_buckets(db, pid)
    return {
        "platform_id": str(pid),
        "slug": platform.slug,
        "name": platform.name,
        "generated_at": now.isoformat(),
        "last_report_at": last_report.isoformat() if last_report else None,
        "last_update_at": max(t for t in (last_report, last_event) if t).isoformat() if (last_report or last_event) else None,
        "cases_total": total - dismissed,
        "cases_open": open_cases,
        "cases_pending": pending,
        "cases_active": active,
        "cases_done": done,
        "cases_high_risk": high_risk,
        "reports_total": _count(db, Report, Report.platform_id == pid, Report.status != "rejected"),
        "reports_last_hour": _count(db, Report, Report.platform_id == pid, Report.created_at >= now - timedelta(hours=1)),
        "reports_last_24h": _count(db, Report, Report.platform_id == pid, Report.created_at >= now - timedelta(hours=24)),
        "clusters_open": _count(db, ReportCluster, ReportCluster.platform_id == pid, ReportCluster.status == "open"),
        "trend_direction": trend_direction(buckets),
        "by_category": _ordered(cat_counts, category_label),
        "by_town": _ordered(town_counts, lambda k: k),
        "by_status": _ordered(status_counts, public_label, [s.value for s in CaseStatus]),
        "by_severity": _ordered(sev_counts, {"critical": "極高", "high": "高", "medium": "中", "low": "低"}.get,
                                ["critical", "high", "medium", "low"]),
        "trend": buckets,
    }


def console_overview(db: Session, platform: Platform) -> dict:
    base = situation(db, platform)
    pid = platform.id
    now = _now()
    dispatch_minutes = []
    resolve_minutes = []
    rows = db.execute(
        select(IncidentCase.created_at, IncidentCase.dispatched_at, IncidentCase.resolved_at)
        .where(IncidentCase.platform_id == pid)
    ).all()
    for created, dispatched, resolved in rows:
        if created and dispatched:
            dispatch_minutes.append((dispatched - created).total_seconds() / 60)
        if created and resolved:
            resolve_minutes.append((resolved - created).total_seconds() / 60)
    role_counts = _group(db, Report.reporter_role, Report.platform_id == pid)
    role_labels = dict(REPORTER_ROLES)
    return {
        **base,
        "cases_new_last_hour": _count(db, IncidentCase, IncidentCase.platform_id == pid,
                                      IncidentCase.created_at >= now - timedelta(hours=1)),
        "reports_unclustered": _count(db, Report, Report.platform_id == pid, Report.cluster_id.is_(None),
                                      Report.status != "rejected"),
        "reports_rejected": _count(db, Report, Report.platform_id == pid, Report.status == "rejected"),
        "median_dispatch_minutes": round(median(dispatch_minutes), 1) if dispatch_minutes else None,
        "median_resolve_minutes": round(median(resolve_minutes), 1) if resolve_minutes else None,
        "by_reporter_role": _ordered(role_counts, lambda k: role_labels.get(k, k)),
    }


def global_overview(db: Session) -> dict:
    now = _now()
    return {
        "platforms_total": _count(db, Platform),
        "platforms_published": _count(db, Platform, Platform.status == "published"),
        "cases_open": _count(db, IncidentCase, IncidentCase.status.not_in((CaseStatus.closed.value, CaseStatus.dismissed.value))),
        "cases_awaiting_dispatch": _count(db, IncidentCase, IncidentCase.status == CaseStatus.awaiting_dispatch.value),
        "cases_active": _count(db, IncidentCase, IncidentCase.status.in_([s.value for s in ACTIVE_STATUSES])),
        "reports_last_24h": _count(db, Report, Report.created_at >= now - timedelta(hours=24)),
    }


# ── map feature collection for the internal layers ────────────────────────
def case_feature(case: IncidentCase, *, public: bool) -> dict:
    lat, lon = (privacy_service.public_coords(case.lat, case.lon) if public else (case.lat, case.lon))
    return {
        "type": "Feature",
        "id": f"case:{case.id}",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "layer": "incident_cases",
            "category_layer": layer_for(case.category),
            "case_id": str(case.id),
            "case_number": case.case_number,
            "title": case.title,
            "category": case.category,
            "category_label": category_label(case.category),
            "severity": case.severity,
            "status": case.status,
            "status_label": public_label(case.status),
            "phase": phase_of(case.status),
            "town": case.town,
            "location_label": case.location_label,
            "report_count": case.report_count,
            "unique_reporter_count": case.unique_reporter_count,
            "assigned_unit": case.assigned_unit,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        },
    }


def cluster_feature(cluster: ReportCluster, *, public: bool) -> dict:
    lat, lon = (privacy_service.public_coords(cluster.centroid_lat, cluster.centroid_lon) if public
                else (cluster.centroid_lat, cluster.centroid_lon))
    return {
        "type": "Feature",
        "id": f"cluster:{cluster.id}",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "layer": "report_clusters",
            "category_layer": layer_for(cluster.category),
            "cluster_id": str(cluster.id),
            "category": cluster.category,
            "category_label": category_label(cluster.category),
            "severity": cluster.severity,
            "status": cluster.status,
            "town": cluster.town,
            "report_count": cluster.report_count,
            "unique_reporter_count": cluster.unique_reporter_count,
            "case_id": str(cluster.case_id) if cluster.case_id else None,
            "first_reported_at": cluster.first_reported_at.isoformat() if cluster.first_reported_at else None,
            "last_reported_at": cluster.last_reported_at.isoformat() if cluster.last_reported_at else None,
        },
    }


def report_feature(report: Report, *, public: bool) -> dict:
    if public:
        props = privacy_service.public_report_properties(report)
        lat, lon = props.pop("lat"), props.pop("lon")
    else:
        lat, lon = report.lat, report.lon
        props = {
            "report_id": str(report.id), "category": report.category, "severity": report.triage_severity,
            "status": report.status, "town": report.town, "address": report.address,
            "description": report.description, "reporter_role": report.reporter_role,
            "photo_count": report.photo_count, "case_id": str(report.case_id) if report.case_id else None,
            "cluster_id": str(report.cluster_id) if report.cluster_id else None,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }
    return {
        "type": "Feature",
        "id": f"report:{report.id}",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"layer": "citizen_reports", "category_layer": layer_for(report.category),
                       "category_label": category_label(report.category), **props},
    }


def map_collection(
    db: Session,
    platform: Platform,
    *,
    public: bool,
    since: datetime | None = None,
    include_reports: bool = True,
) -> dict:
    pid = platform.id
    feats: list[dict] = []
    cq = select(IncidentCase).where(IncidentCase.platform_id == pid)
    if public:
        cq = cq.where(IncidentCase.status != CaseStatus.dismissed.value)
    if since is not None:
        cq = cq.where(IncidentCase.created_at >= since)
    for case in db.scalars(cq.order_by(IncidentCase.created_at.desc()).limit(2000)).all():
        feats.append(case_feature(case, public=public))
    clq = select(ReportCluster).where(ReportCluster.platform_id == pid, ReportCluster.status == "open")
    if since is not None:
        clq = clq.where(ReportCluster.last_reported_at >= since)
    for cluster in db.scalars(clq.order_by(ReportCluster.last_reported_at.desc()).limit(2000)).all():
        feats.append(cluster_feature(cluster, public=public))
    if include_reports:
        rq = select(Report).where(Report.platform_id == pid, Report.lat.is_not(None), Report.status != "rejected")
        if since is not None:
            rq = rq.where(Report.created_at >= since)
        for report in db.scalars(rq.order_by(Report.created_at.desc()).limit(5000)).all():
            feats.append(report_feature(report, public=public))
    return {"type": "FeatureCollection", "features": feats, "generated_at": _now().isoformat()}
