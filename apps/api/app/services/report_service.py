"""Citizen report intake (modules: report_form, report_category, geo_location,
reporter_role, severity_triage) and the hand-off into the clustering engine.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IncidentCase, Platform, Report, ReportCluster
from app.domain.categories import CATEGORIES, REPORTER_ROLE_KEYS, escalate
from app.schemas.report import ReportCreate
from app.services import cluster_service, outbox_service, privacy_service
from app.utils.geo import TOWN_CENTROIDS, haversine_m, normalize_admin


class PlatformNotAcceptingError(Exception):
    pass


class InvalidCategoryError(Exception):
    def __init__(self, category: str, allowed: list[str]) -> None:
        super().__init__(f"Category '{category}' is not enabled on this platform.")
        self.category = category
        self.allowed = allowed


def allowed_categories(platform: Platform) -> list[str]:
    cats = (platform.scenario or {}).get("report_categories") or []
    keys = [c.get("key") for c in cats if isinstance(c, dict) and c.get("key") in CATEGORIES]
    return keys or list(CATEGORIES.keys())


def nearest_town(platform: Platform, lat: float | None, lon: float | None) -> str | None:
    """Assign a township by nearest known town centre within the platform's
    county. Good enough for filters/statistics; not an authoritative geocode."""
    if lat is None or lon is None:
        return None
    county = normalize_admin(platform.county)
    towns = TOWN_CENTROIDS.get(county)
    if not towns:
        return None
    wanted = set(platform.towns or []) or set(towns.keys())
    best: tuple[float, str] | None = None
    for name, (tlat, tlon) in towns.items():
        if wanted and name not in wanted and len(wanted) < len(towns):
            # still consider all towns, but prefer the platform's listed ones
            pass
        d = haversine_m(lat, lon, tlat, tlon)
        if best is None or d < best[0]:
            best = (d, name)
    return best[1] if best else None


def create_report(
    db: Session,
    platform: Platform,
    payload: ReportCreate,
    *,
    client_key: str | None = None,
    source: str = "web",
    created_at: datetime | None = None,
) -> tuple[Report, ReportCluster | None, IncidentCase | None]:
    """Insert the report, cluster it, maybe create a case — one transaction."""
    if platform.status == "archived":
        raise PlatformNotAcceptingError()
    allowed = allowed_categories(platform)
    if payload.category not in allowed:
        raise InvalidCategoryError(payload.category, allowed)

    role = payload.reporter_role if payload.reporter_role in REPORTER_ROLE_KEYS else "citizen"
    stated = payload.severity or CATEGORIES[payload.category].default_severity
    triaged = escalate(stated, payload.category, role)
    town = payload.town or nearest_town(platform, payload.lat, payload.lon)

    report = Report(
        platform_id=platform.id,
        category=payload.category,
        description=payload.description,
        severity=stated,
        triage_severity=triaged,
        lat=payload.lat,
        lon=payload.lon,
        town=town,
        address=payload.address,
        reporter_role=role,
        reporter_name=payload.reporter_name,
        reporter_contact=payload.reporter_contact,
        reporter_key=privacy_service.reporter_key(payload.reporter_contact, client_key),
        status="received",
        source=source,
        raw_payload=payload.model_dump(mode="json", exclude={"reporter_name", "reporter_contact"}),
    )
    if created_at is not None:
        report.created_at = created_at
        report.updated_at = created_at
    db.add(report)
    db.flush()
    if report.created_at is None:  # server default not yet loaded
        db.refresh(report)

    outbox_service.enqueue_event(
        db,
        event_type="report.created",
        aggregate_id=report.id,
        payload={
            "platform_id": str(platform.id),
            "report_id": str(report.id),
            "category": report.category,
            "triage_severity": report.triage_severity,
            "reporter_role": report.reporter_role,
            "geolocated": report.lat is not None,
            "source": source,
        },
    )

    cluster, case = cluster_service.process_report(db, platform, report)
    db.commit()
    db.refresh(report)
    if cluster is not None:
        db.refresh(cluster)
    if case is not None:
        db.refresh(case)
    return report, cluster, case


def list_reports(
    db: Session,
    platform_id: uuid.UUID,
    *,
    category: str | None = None,
    town: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Report], int]:
    filters = [Report.platform_id == platform_id]
    if category:
        filters.append(Report.category == category)
    if town:
        filters.append(Report.town == town)
    if status:
        filters.append(Report.status == status)
    if severity:
        filters.append(Report.triage_severity == severity)
    if since is not None:
        filters.append(Report.created_at >= since)
    total = db.scalar(select(func.count()).select_from(Report).where(*filters)) or 0
    rows = db.scalars(
        select(Report).where(*filters).order_by(Report.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), int(total)


def get_report(db: Session, report_id: uuid.UUID) -> Report | None:
    return db.get(Report, report_id)


def reject_report(db: Session, report: Report, *, note: str | None = None) -> Report:
    """Operator marks a report as not credible; it is removed from the cluster
    count and recounted."""
    report.status = "rejected"
    db.flush()
    outbox_service.enqueue_event(
        db, event_type="report.rejected", aggregate_id=report.id,
        payload={"platform_id": str(report.platform_id), "report_id": str(report.id), "note": note},
    )
    if report.cluster_id:
        cluster = db.get(ReportCluster, report.cluster_id)
        platform = db.get(Platform, report.platform_id)
        if cluster is not None and platform is not None:
            cluster_service._recount(db, cluster, cluster_service.policy_for(platform))
            if cluster.case_id:
                case = db.get(IncidentCase, cluster.case_id)
                if case is not None:
                    case.report_count = cluster.report_count
                    case.unique_reporter_count = cluster.unique_reporter_count
    db.commit()
    db.refresh(report)
    return report
