"""Retire the ResQLink-era tables that AidFlow no longer uses.

The platform/report/case model in 0010 supersedes incidents, generated
artifacts + review tasks, the volunteer/supply resource pool, publications and
generic form submissions. Dropping them keeps a cloned database free of dead
tables; ``downgrade`` recreates them with their final (0009) shape so a
rollback to the ResQLink schema is still possible.

Revision ID: 0011_retire_resqlink_tables
Revises: 0010_aidflow_core
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_retire_resqlink_tables"
down_revision: Union[str, None] = "0010_aidflow_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RETIRED = (
    "form_submissions",
    "publications",
    "assignments",
    "resource_offers",
    "review_tasks",
    "generated_artifacts",
    "disaster_reports",
    "incidents",
)


def upgrade() -> None:
    for table in _RETIRED:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=nullable
    )


def downgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("scenario_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("county", sa.Text(), nullable=True),
        sa.Column("town", sa.Text(), nullable=True),
        sa.Column("river", sa.Text(), nullable=True),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("aoi_geojson", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incidents_slug"), "incidents", ["slug"], unique=True)

    op.create_table(
        "generated_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending_review", nullable=False),
        sa.Column("risk_level", sa.Text(), server_default="medium", nullable=False),
        sa.Column("created_by", sa.Text(), server_default="system", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "artifact_type", "status"):
        op.create_index(op.f(f"ix_generated_artifacts_{col}"), "generated_artifacts", [col])

    op.create_table(
        "review_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), server_default="medium", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["generated_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "artifact_id", "status"):
        op.create_index(op.f(f"ix_review_tasks_{col}"), "review_tasks", [col])

    op.create_table(
        "disaster_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reporter_name", sa.Text(), nullable=True),
        sa.Column("reporter_contact", sa.Text(), nullable=True),
        sa.Column("need_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), server_default="medium", nullable=False),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        sa.Column("verification_status", sa.Text(), server_default="unverified", nullable=False),
        sa.Column("triage_priority", sa.Text(), server_default="normal", nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "need_type", "severity", "status", "verification_status",
                "triage_priority", "created_at"):
        op.create_index(op.f(f"ix_disaster_reports_{col}"), "disaster_reports", [col])

    op.create_table(
        "resource_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_type", sa.Text(), nullable=False),
        sa.Column("item", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("provider_name", sa.Text(), nullable=True),
        sa.Column("provider_contact", sa.Text(), nullable=True),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("available_time", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "offer_type", "status", "created_at"):
        op.create_index(op.f(f"ix_resource_offers_{col}"), "resource_offers", [col])

    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="assigned", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["disaster_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["resource_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "report_id", "offer_id", "status", "created_at"):
        op.create_index(op.f(f"ix_assignments_{col}"), "assignments", [col])

    op.create_table(
        "publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("connector", sa.Text(), server_default="simulated", nullable=False),
        sa.Column("status", sa.Text(), server_default="published", nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["generated_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "artifact_id", "channel", "status", "created_at"):
        op.create_index(op.f(f"ix_publications_{col}"), "publications", [col])

    op.create_table(
        "form_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("form_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["generated_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "artifact_id", "form_key", "created_at"):
        op.create_index(op.f(f"ix_form_submissions_{col}"), "form_submissions", [col])
