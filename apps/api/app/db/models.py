"""AidFlow persistence model.

One *Platform* per disaster (generated from a scenario brief). Citizens file
*Reports* against a platform; the deterministic clustering engine groups them
into *ReportClusters*; when enough distinct reporters agree a cluster is
promoted to an *IncidentCase*, which the government console drives through the
case state machine. Every transition is recorded as a *CaseEvent* (the public
timeline) and mirrored to the transactional *EventOutbox* (audit trail).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EventOutbox(Base):
    """Transactional outbox: every domain change is written here in the same
    transaction as its business data. Read-models (platform timeline, audit
    log) are derived from it."""

    __tablename__ = "event_outbox"

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = _created_at()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Platform(Base):
    """A generated disaster platform: one public portal + one console."""

    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # the original natural-language brief the platform was generated from
    brief: Mapped[str | None] = mapped_column(Text, nullable=True)

    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    towns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    hazards: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    primary_hazard: Mapped[str] = mapped_column(
        Text, nullable=False, default="generic", server_default="generic"
    )
    # snapshot of the composed scenario profile (report categories, roles, labels)
    scenario: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft", index=True
    )
    modules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    layers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # cluster_policy, map centre/zoom, contacts, …
    configuration: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    center_lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    center_lon: Mapped[float | None] = mapped_column(Double, nullable=True)

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformModuleConfig(Base):
    """Per-platform module/layer enablement + configuration."""

    __tablename__ = "platform_module_configs"
    __table_args__ = (UniqueConstraint("platform_id", "module_id", name="uq_platform_module"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_id: Mapped[str] = mapped_column(Text, nullable=False)
    module_type: Mapped[str] = mapped_column(Text, nullable=False, default="feature", server_default="feature")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created_at()


class Report(Base):
    """A single citizen (or field) report. reporter_name / reporter_contact /
    address are PII — they never leave the internal API."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_platform_created", "platform_id", "created_at"),
        Index("ix_reports_platform_status", "platform_id", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # severity as stated by the reporter, and after deterministic triage
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default="medium")
    triage_severity: Mapped[str] = mapped_column(
        Text, nullable=False, default="medium", server_default="medium", index=True
    )
    lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    lon: Mapped[float | None] = mapped_column(Double, nullable=True)
    town: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    reporter_role: Mapped[str] = mapped_column(
        Text, nullable=False, default="citizen", server_default="citizen"
    )
    reporter_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    # opaque identity hash used ONLY to count unique reporters; null = anonymous
    reporter_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="received", server_default="received"
    )
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_clusters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    photo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="web", server_default="web")
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class ReportCluster(Base):
    """Reports of similar category, close in space and time. Deterministic —
    the engine in cluster_service decides membership, never a model."""

    __tablename__ = "report_clusters"
    __table_args__ = (Index("ix_clusters_platform_status", "platform_id", "status"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default="medium")
    centroid_lat: Mapped[float] = mapped_column(Double, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Double, nullable=False)
    town: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    unique_reporter_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # open | promoted | closed | dismissed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class IncidentCase(Base):
    """A formal government case. Status is a CaseStatus value (domain enum)."""

    __tablename__ = "incident_cases"
    __table_args__ = (
        Index("ix_cases_platform_status", "platform_id", "status"),
        Index("ix_cases_platform_created", "platform_id", "created_at"),
        UniqueConstraint("platform_id", "case_number", name="uq_incident_cases_platform_case_number"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_clusters.id", ondelete="SET NULL"), nullable=True
    )
    # human-readable, unique within the platform (e.g. NT-20260821-0007)
    case_number: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default="medium", index=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="awaiting_dispatch", server_default="awaiting_dispatch"
    )
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    town: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    # public-safe place description (no house numbers, no names)
    location_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    unique_reporter_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    assigned_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    threshold_reached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class CaseAssignment(Base):
    """Who was sent. Contact details are internal only."""

    __tablename__ = "case_assignments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_name: Mapped[str] = mapped_column(Text, nullable=False)
    team_lead: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # active | completed | cancelled
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default="active")
    # dispatch integration (0013)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responder_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    route_geojson: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    route_source: Mapped[str | None] = mapped_column(Text, nullable=True)  # osrm | straight_line
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    notified_via: Mapped[str | None] = mapped_column(Text, nullable=True)  # line | webhook | simulated
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class ResponderUnit(Base):
    """A unit that can be dispatched: fire stations from open data (surveyed
    coordinates) or configured agencies (indicative township-centre
    positions). ``line_to`` is the unit's LINE user/group id for real pushes."""

    __tablename__ = "responder_units"
    __table_args__ = (UniqueConstraint("county", "external_id", name="uq_responder_units_county_external"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    county: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    town: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    # open_data | configured | indicative
    location_source: Mapped[str] = mapped_column(Text, nullable=False, default="indicative", server_default="indicative")
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    line_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class VehiclePosition(Base):
    """AVL pings pushed by a fleet system (POST /v1/avl/positions). When a
    unit has fresh pings, they replace the dispatch simulation."""

    __tablename__ = "vehicle_positions"
    __table_args__ = (Index("ix_vehicle_positions_vehicle_time", "vehicle_id", "recorded_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responder_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    vehicle_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="works_truck", server_default="works_truck")
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    heading: Mapped[float | None] = mapped_column(Double, nullable=True)
    speed_kmh: Mapped[float | None] = mapped_column(Double, nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created_at()


class CaseEvent(Base):
    """Audit-grade case history. ``public`` rows form the public timeline."""

    __tablename__ = "case_events"
    __table_args__ = (Index("ix_case_events_case_created", "case_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    # system | citizen | operator
    actor_role: Mapped[str] = mapped_column(Text, nullable=False, default="system", server_default="system")
    actor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created_at()


class ReportPhoto(Base):
    """Image abstraction: the DB stores metadata + a storage key; bytes live in
    the media store (local filesystem by default)."""

    __tablename__ = "report_photos"

    id: Mapped[uuid.UUID] = _uuid_pk()
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # scene | before | after
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="scene", server_default="scene")
    # citizen | agency
    source: Mapped[str] = mapped_column(Text, nullable=False, default="citizen", server_default="citizen")
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = _created_at()
