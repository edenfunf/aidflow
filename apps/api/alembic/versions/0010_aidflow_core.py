"""AidFlow core schema: platforms, reports, clusters, cases, events, photos.

Revision ID: 0010_aidflow_core
Revises: 0009_publication_url
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_aidflow_core"
down_revision: Union[str, None] = "0009_publication_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _ts(name: str, nullable: bool = False, default_now: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default_now else None,
        nullable=nullable,
    )


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(
        name, postgresql.JSONB(astext_type=sa.Text()), server_default=default, nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "platforms",
        _uuid("id"),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("county", sa.Text(), nullable=True),
        _jsonb("towns", "[]"),
        _jsonb("hazards", "[]"),
        sa.Column("primary_hazard", sa.Text(), server_default="generic", nullable=False),
        _jsonb("scenario", "{}"),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        _jsonb("modules", "[]"),
        _jsonb("layers", "[]"),
        _jsonb("configuration", "{}"),
        sa.Column("center_lat", sa.Double(), nullable=True),
        sa.Column("center_lon", sa.Double(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("published_at", nullable=True, default_now=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_platforms_slug"), "platforms", ["slug"], unique=True)
    op.create_index(op.f("ix_platforms_status"), "platforms", ["status"], unique=False)

    op.create_table(
        "platform_module_configs",
        _uuid("id"),
        _uuid("platform_id"),
        sa.Column("module_id", sa.Text(), nullable=False),
        sa.Column("module_type", sa.Text(), server_default="feature", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        _jsonb("config", "{}"),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_id", "module_id", name="uq_platform_module"),
    )
    op.create_index(
        op.f("ix_platform_module_configs_platform_id"),
        "platform_module_configs",
        ["platform_id"],
        unique=False,
    )

    # incident_cases and report_clusters reference each other; create cases
    # first without the cluster FK, then clusters, then add the FK.
    op.create_table(
        "incident_cases",
        _uuid("id"),
        _uuid("platform_id"),
        _uuid("cluster_id", nullable=True),
        sa.Column("case_number", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), server_default="medium", nullable=False),
        sa.Column("status", sa.Text(), server_default="awaiting_dispatch", nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("town", sa.Text(), nullable=True),
        sa.Column("location_label", sa.Text(), nullable=True),
        sa.Column("report_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unique_reporter_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assigned_unit", sa.Text(), nullable=True),
        sa.Column("public_summary", sa.Text(), nullable=True),
        _ts("threshold_reached_at", nullable=True, default_now=False),
        _ts("dispatched_at", nullable=True, default_now=False),
        _ts("resolved_at", nullable=True, default_now=False),
        _ts("closed_at", nullable=True, default_now=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_number", name="uq_incident_cases_case_number"),
    )
    op.create_index(op.f("ix_incident_cases_platform_id"), "incident_cases", ["platform_id"])
    op.create_index(op.f("ix_incident_cases_category"), "incident_cases", ["category"])
    op.create_index(op.f("ix_incident_cases_severity"), "incident_cases", ["severity"])
    op.create_index(op.f("ix_incident_cases_town"), "incident_cases", ["town"])
    op.create_index("ix_cases_platform_status", "incident_cases", ["platform_id", "status"])
    op.create_index("ix_cases_platform_created", "incident_cases", ["platform_id", "created_at"])

    op.create_table(
        "report_clusters",
        _uuid("id"),
        _uuid("platform_id"),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), server_default="medium", nullable=False),
        sa.Column("centroid_lat", sa.Double(), nullable=False),
        sa.Column("centroid_lon", sa.Double(), nullable=False),
        sa.Column("town", sa.Text(), nullable=True),
        sa.Column("report_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unique_reporter_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        _uuid("case_id", nullable=True),
        _ts("first_reported_at", default_now=False),
        _ts("last_reported_at", default_now=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_report_clusters_platform_id"), "report_clusters", ["platform_id"])
    op.create_index(op.f("ix_report_clusters_case_id"), "report_clusters", ["case_id"])
    op.create_index("ix_clusters_platform_status", "report_clusters", ["platform_id", "status"])

    op.create_foreign_key(
        "fk_incident_cases_cluster_id",
        "incident_cases",
        "report_clusters",
        ["cluster_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "reports",
        _uuid("id"),
        _uuid("platform_id"),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), server_default="medium", nullable=False),
        sa.Column("triage_severity", sa.Text(), server_default="medium", nullable=False),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("town", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("reporter_role", sa.Text(), server_default="citizen", nullable=False),
        sa.Column("reporter_name", sa.Text(), nullable=True),
        sa.Column("reporter_contact", sa.Text(), nullable=True),
        sa.Column("reporter_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="received", nullable=False),
        _uuid("cluster_id", nullable=True),
        _uuid("case_id", nullable=True),
        sa.Column("photo_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.Text(), server_default="web", nullable=False),
        _jsonb("raw_payload", "{}"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["report_clusters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("platform_id", "category", "triage_severity", "town", "reporter_key",
                "cluster_id", "case_id"):
        op.create_index(op.f(f"ix_reports_{col}"), "reports", [col], unique=False)
    op.create_index("ix_reports_platform_created", "reports", ["platform_id", "created_at"])
    op.create_index("ix_reports_platform_status", "reports", ["platform_id", "status"])

    op.create_table(
        "case_assignments",
        _uuid("id"),
        _uuid("case_id"),
        _uuid("platform_id"),
        sa.Column("unit_name", sa.Text(), nullable=False),
        sa.Column("team_lead", sa.Text(), nullable=True),
        sa.Column("contact", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_case_assignments_case_id"), "case_assignments", ["case_id"])
    op.create_index(op.f("ix_case_assignments_platform_id"), "case_assignments", ["platform_id"])

    op.create_table(
        "case_events",
        _uuid("id"),
        _uuid("case_id"),
        _uuid("platform_id"),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("actor_role", sa.Text(), server_default="system", nullable=False),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("public", sa.Boolean(), server_default="true", nullable=False),
        _jsonb("payload", "{}"),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_case_events_case_id"), "case_events", ["case_id"])
    op.create_index(op.f("ix_case_events_platform_id"), "case_events", ["platform_id"])
    op.create_index("ix_case_events_case_created", "case_events", ["case_id", "created_at"])

    op.create_table(
        "report_photos",
        _uuid("id"),
        _uuid("report_id", nullable=True),
        _uuid("case_id", nullable=True),
        _uuid("platform_id"),
        sa.Column("kind", sa.Text(), server_default="scene", nullable=False),
        sa.Column("source", sa.Text(), server_default="citizen", nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("public", sa.Boolean(), server_default="true", nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_report_photos_report_id"), "report_photos", ["report_id"])
    op.create_index(op.f("ix_report_photos_case_id"), "report_photos", ["case_id"])
    op.create_index(op.f("ix_report_photos_platform_id"), "report_photos", ["platform_id"])


def downgrade() -> None:
    op.drop_table("report_photos")
    op.drop_table("case_events")
    op.drop_table("case_assignments")
    op.drop_table("reports")
    op.drop_constraint("fk_incident_cases_cluster_id", "incident_cases", type_="foreignkey")
    op.drop_table("report_clusters")
    op.drop_table("incident_cases")
    op.drop_table("platform_module_configs")
    op.drop_table("platforms")
