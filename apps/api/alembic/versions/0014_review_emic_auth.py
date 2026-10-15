"""Review gate, EMIC / community handling, reporter subscriptions, staff
accounts, notification log and LINE groups; retire dispatch and vehicles.

南投縣政府 2026-09-03 需求：成案後先經承辦審核，分流為「上報 EMIC」或
「民間可處理」；派遣／出勤車輛功能下架。

Revision ID: 0014_review_emic_auth
Revises: 0013_responders_dispatch
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_review_emic_auth"
down_revision: Union[str, None] = "0013_responders_dispatch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# old dispatch statuses → new review / EMIC flow
_STATUS_UP = {
    "reported": "pending_review",
    "verifying": "pending_review",
    "threshold_reached": "pending_review",
    "awaiting_dispatch": "pending_review",
    "assigned": "emic_processing",
    "en_route": "emic_processing",
    "on_site": "emic_processing",
    "processing": "emic_processing",
    "resolved": "closed",
}
_STATUS_DOWN = {
    "pending_review": "awaiting_dispatch",
    "reported_emic": "processing",
    "emic_processing": "processing",
    "community_open": "awaiting_dispatch",
    "community_submitted": "awaiting_dispatch",
}


def _ts(name: str, nullable: bool = False, default_now: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable,
                     server_default=sa.text("now()") if default_now else None)


def _remap(mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        op.execute(sa.text("UPDATE incident_cases SET status = :new WHERE status = :old").bindparams(old=old, new=new))
        op.execute(sa.text("UPDATE case_events SET to_status = :new WHERE to_status = :old").bindparams(old=old, new=new))
        op.execute(sa.text("UPDATE case_events SET from_status = :new WHERE from_status = :old").bindparams(old=old, new=new))


def upgrade() -> None:
    # ── incident_cases ────────────────────────────────────────────────────
    for col in ("track", "reviewed_by", "emic_case_no", "emic_status", "emic_channel"):
        op.add_column("incident_cases", sa.Column(col, sa.Text(), nullable=True))
    for col in ("reviewed_at", "emic_reported_at", "emic_synced_at", "community_submitted_at"):
        op.add_column("incident_cases", _ts(col, nullable=True, default_now=False))
    op.create_index(op.f("ix_incident_cases_track"), "incident_cases", ["track"])

    # a case that was ever dispatched was handled by an agency: call it the EMIC track
    op.execute("""
        UPDATE incident_cases
           SET track = 'emic', emic_channel = 'manual', reviewed_at = dispatched_at,
               emic_reported_at = dispatched_at
         WHERE dispatched_at IS NOT NULL
    """)
    _remap(_STATUS_UP)
    op.alter_column("incident_cases", "status", server_default="pending_review")
    op.drop_column("incident_cases", "dispatched_at")

    # ── reports: optional e-mail + progress subscription ──────────────────
    op.add_column("reports", sa.Column("reporter_email", sa.Text(), nullable=True))
    op.add_column("reports", sa.Column("notify_opt_in", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("reports", sa.Column("notify_token", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_reports_notify_token", "reports", ["notify_token"])

    # ── staff accounts ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        _ts("locked_until", nullable=True, default_now=False),
        _ts("last_login_at", nullable=True, default_now=False),
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    # ── notification log ──────────────────────────────────────────────────
    op.create_table(
        "notification_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_logs_platform_id"), "notification_logs", ["platform_id"])
    op.create_index(op.f("ix_notification_logs_case_id"), "notification_logs", ["case_id"])
    op.create_index("ix_notification_logs_platform_created", "notification_logs", ["platform_id", "created_at"])

    # ── LINE groups the bot has joined ────────────────────────────────────
    op.create_table(
        "line_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", sa.Text(), nullable=False),
        sa.Column("platform_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default="joined", nullable=False),
        _ts("bound_at", nullable=True, default_now=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", name="uq_line_groups_group_id"),
    )
    op.create_index(op.f("ix_line_groups_platform_id"), "line_groups", ["platform_id"])

    # ── retire dispatch: assignments, vehicles, responder units ───────────
    op.drop_table("vehicle_positions")
    op.drop_table("case_assignments")
    op.drop_table("responder_units")


def downgrade() -> None:
    op.create_table(
        "responder_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("county", sa.Text(), nullable=False),
        sa.Column("town", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("location_source", sa.Text(), server_default="indicative", nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("line_to", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("county", "external_id", name="uq_responder_units_county_external"),
    )
    op.create_index(op.f("ix_responder_units_county"), "responder_units", ["county"])
    op.create_index(op.f("ix_responder_units_kind"), "responder_units", ["kind"])
    op.create_table(
        "case_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_name", sa.Text(), nullable=False),
        sa.Column("team_lead", sa.Text(), nullable=True),
        sa.Column("contact", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("route_geojson", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("route_source", sa.Text(), nullable=True),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("eta_minutes", sa.Integer(), nullable=True),
        sa.Column("vehicles", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("notified_via", sa.Text(), nullable=True),
        _ts("notified_at", nullable=True, default_now=False),
        _ts("departed_at", nullable=True, default_now=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["responder_units.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_case_assignments_case_id"), "case_assignments", ["case_id"])
    op.create_index(op.f("ix_case_assignments_platform_id"), "case_assignments", ["platform_id"])
    op.create_index(op.f("ix_case_assignments_unit_id"), "case_assignments", ["unit_id"])
    op.create_table(
        "vehicle_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vehicle_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default="works_truck", nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("heading", sa.Double(), nullable=True),
        sa.Column("speed_kmh", sa.Double(), nullable=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=True),
        _ts("recorded_at", default_now=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["unit_id"], ["responder_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vehicle_positions_unit_id"), "vehicle_positions", ["unit_id"])
    op.create_index(op.f("ix_vehicle_positions_case_id"), "vehicle_positions", ["case_id"])
    op.create_index(op.f("ix_vehicle_positions_recorded_at"), "vehicle_positions", ["recorded_at"])
    op.create_index("ix_vehicle_positions_vehicle_time", "vehicle_positions", ["vehicle_id", "recorded_at"])

    op.drop_table("line_groups")
    op.drop_table("notification_logs")
    op.drop_table("users")

    op.drop_constraint("uq_reports_notify_token", "reports", type_="unique")
    for col in ("notify_token", "notify_opt_in", "reporter_email"):
        op.drop_column("reports", col)

    op.add_column("incident_cases", _ts("dispatched_at", nullable=True, default_now=False))
    op.execute("UPDATE incident_cases SET dispatched_at = reviewed_at WHERE track = 'emic'")
    _remap(_STATUS_DOWN)
    op.alter_column("incident_cases", "status", server_default="awaiting_dispatch")
    op.drop_index(op.f("ix_incident_cases_track"), table_name="incident_cases")
    for col in ("community_submitted_at", "emic_synced_at", "emic_reported_at", "reviewed_at",
                "emic_channel", "emic_status", "emic_case_no", "reviewed_by", "track"):
        op.drop_column("incident_cases", col)
