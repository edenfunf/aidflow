"""Deterministic geo-clustering + the N-unique-reporter trigger
(modules: geo_cluster, duplicate_report_merge, two_report_trigger,
incident_case_creation).

No model is involved anywhere on this path. A report joins the nearest *open*
cluster of a similar category within ``radius_meters`` whose last report is
within ``time_window_minutes``; otherwise it starts a new cluster. Unique
reporters are counted by the opaque ``reporter_key`` (the same person sending
twice counts once). When a cluster reaches ``required_unique_reporters`` it is
promoted to an IncidentCase exactly once.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IncidentCase, Platform, Report, ReportCluster
from app.domain.categories import are_similar, max_severity
from app.services import outbox_service
from app.utils.geo import bbox_for, haversine_m


@dataclass(frozen=True)
class ClusterPolicy:
    required_unique_reporters: int = 2
    radius_meters: int = 100
    time_window_minutes: int = 60
    count_anonymous_reporters: bool = True

    def to_dict(self) -> dict:
        return {
            "required_unique_reporters": self.required_unique_reporters,
            "radius_meters": self.radius_meters,
            "time_window_minutes": self.time_window_minutes,
            "count_anonymous_reporters": self.count_anonymous_reporters,
        }


def policy_from_dict(raw: dict | None) -> ClusterPolicy:
    """Merge a platform's cluster_policy over the configured defaults and clamp
    to sane bounds (a misconfigured platform must not break clustering)."""
    base = settings.default_cluster_policy
    merged = {**base, **{k: v for k, v in (raw or {}).items() if v is not None}}
    try:
        required = max(1, int(merged["required_unique_reporters"]))
        radius = min(max(10, int(merged["radius_meters"])), 5000)
        window = min(max(1, int(merged["time_window_minutes"])), 7 * 24 * 60)
        anon = bool(merged.get("count_anonymous_reporters", True))
    except (TypeError, ValueError):
        return ClusterPolicy(**base)
    return ClusterPolicy(required, radius, window, anon)


def policy_for(platform: Platform) -> ClusterPolicy:
    return policy_from_dict((platform.configuration or {}).get("cluster_policy"))


# ── pure matching logic (unit-tested without a database) ─────────────────
@dataclass(frozen=True)
class ClusterCandidate:
    id: object
    category: str
    lat: float
    lon: float
    last_reported_at: datetime


def pick_cluster(
    candidates: list[ClusterCandidate],
    *,
    lat: float,
    lon: float,
    category: str,
    reported_at: datetime,
    policy: ClusterPolicy,
) -> ClusterCandidate | None:
    """Nearest candidate that is similar in category, within radius and within
    the time window. Ties are broken by distance, then by recency."""
    window = timedelta(minutes=policy.time_window_minutes)
    best: tuple[float, float, ClusterCandidate] | None = None
    for c in candidates:
        if not are_similar(c.category, category):
            continue
        if reported_at - c.last_reported_at > window:
            continue
        if c.last_reported_at - reported_at > window:
            continue
        d = haversine_m(lat, lon, c.lat, c.lon)
        if d > policy.radius_meters:
            continue
        key = (d, -c.last_reported_at.timestamp())
        if best is None or key < best[:2]:
            best = (key[0], key[1], c)
    return best[2] if best else None


def count_unique_reporters(reporter_keys: list[str | None], *, count_anonymous: bool) -> int:
    """The same key counts once; anonymous reports (None) each count as one
    person only when the policy allows it."""
    keyed = {k for k in reporter_keys if k}
    anon = sum(1 for k in reporter_keys if not k) if count_anonymous else 0
    return len(keyed) + anon


# ── database side ────────────────────────────────────────────────────────
def _open_candidates(
    db: Session, platform_id: uuid.UUID, lat: float, lon: float, reported_at: datetime, policy: ClusterPolicy
) -> list[ReportCluster]:
    min_lat, min_lon, max_lat, max_lon = bbox_for(lat, lon, policy.radius_meters)
    since = reported_at - timedelta(minutes=policy.time_window_minutes)
    rows = db.scalars(
        select(ReportCluster).where(
            and_(
                ReportCluster.platform_id == platform_id,
                ReportCluster.status.in_(("open", "promoted")),
                ReportCluster.centroid_lat.between(min_lat, max_lat),
                ReportCluster.centroid_lon.between(min_lon, max_lon),
                ReportCluster.last_reported_at >= since,
            )
        )
    ).all()
    return list(rows)


def _recount(db: Session, cluster: ReportCluster, policy: ClusterPolicy) -> None:
    rows = db.execute(
        select(Report.reporter_key, Report.lat, Report.lon, Report.triage_severity, Report.created_at)
        .where(Report.cluster_id == cluster.id, Report.status != "rejected")
    ).all()
    keys = [r[0] for r in rows]
    points = [(r[1], r[2]) for r in rows if r[1] is not None and r[2] is not None]
    cluster.report_count = len(rows)
    cluster.unique_reporter_count = count_unique_reporters(
        keys, count_anonymous=policy.count_anonymous_reporters
    )
    if points:
        cluster.centroid_lat = sum(p[0] for p in points) / len(points)
        cluster.centroid_lon = sum(p[1] for p in points) / len(points)
    cluster.severity = max_severity([r[3] for r in rows]) if rows else cluster.severity
    if rows:
        cluster.first_reported_at = min(r[4] for r in rows)
        cluster.last_reported_at = max(r[4] for r in rows)


def process_report(
    db: Session, platform: Platform, report: Report, *, policy: ClusterPolicy | None = None
) -> tuple[ReportCluster | None, IncidentCase | None]:
    """Attach a geolocated report to a cluster (or open one) and promote the
    cluster to a case when the unique-reporter threshold is met. Does not
    commit — the caller owns the transaction."""
    from app.services import case_service  # local import: case_service imports this module

    if report.lat is None or report.lon is None:
        return None, None
    policy = policy or policy_for(platform)
    reported_at = report.created_at or datetime.now(tz=None)

    candidates = _open_candidates(db, platform.id, report.lat, report.lon, reported_at, policy)
    chosen = pick_cluster(
        [ClusterCandidate(c.id, c.category, c.centroid_lat, c.centroid_lon, c.last_reported_at)
         for c in candidates],
        lat=report.lat, lon=report.lon, category=report.category,
        reported_at=reported_at, policy=policy,
    )
    cluster: ReportCluster
    if chosen is None:
        cluster = ReportCluster(
            platform_id=platform.id,
            category=report.category,
            severity=report.triage_severity,
            centroid_lat=report.lat,
            centroid_lon=report.lon,
            town=report.town,
            report_count=0,
            unique_reporter_count=0,
            status="open",
            first_reported_at=reported_at,
            last_reported_at=reported_at,
        )
        db.add(cluster)
        db.flush()
        outbox_service.enqueue_event(
            db, event_type="cluster.opened", aggregate_id=cluster.id,
            payload={"platform_id": str(platform.id), "cluster_id": str(cluster.id),
                     "category": report.category, "report_id": str(report.id)},
        )
    else:
        cluster = next(c for c in candidates if c.id == chosen.id)

    report.cluster_id = cluster.id
    report.status = "clustered"
    if not cluster.town and report.town:
        cluster.town = report.town
    db.flush()
    _recount(db, cluster, policy)
    db.flush()

    created_case: IncidentCase | None = None
    if cluster.case_id is not None:
        # already a case: the new report joins it (and is visible on the timeline)
        case = db.get(IncidentCase, cluster.case_id)
        if case is not None:
            case_service.attach_report_to_case(db, case, report, cluster)
    elif cluster.unique_reporter_count >= policy.required_unique_reporters:
        created_case = case_service.create_case_from_cluster(
            db, platform, cluster, trigger="threshold", policy=policy
        )
    return cluster, created_case


def list_clusters(
    db: Session, platform_id: uuid.UUID, *, status: str | None = None, limit: int = 200
) -> list[ReportCluster]:
    q = select(ReportCluster).where(ReportCluster.platform_id == platform_id)
    if status:
        q = q.where(ReportCluster.status == status)
    return list(db.scalars(q.order_by(ReportCluster.last_reported_at.desc()).limit(limit)).all())


def cluster_reporter_breakdown(db: Session, cluster_id: uuid.UUID) -> dict:
    rows = db.execute(
        select(Report.reporter_role, func.count()).where(Report.cluster_id == cluster_id)
        .group_by(Report.reporter_role)
    ).all()
    return {role: int(n) for role, n in rows}
