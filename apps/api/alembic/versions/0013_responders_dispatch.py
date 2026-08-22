"""Responder units, dispatch routes/vehicles on assignments, AVL positions.

Revision ID: 0013_responders_dispatch
Revises: 0012_case_number_per_platform
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_responders_dispatch"
down_revision: Union[str, None] = "0012_case_number_per_platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("county", "external_id", name="uq_responder_units_county_external"),
    )
    op.create_index(op.f("ix_responder_units_county"), "responder_units", ["county"])
    op.create_index(op.f("ix_responder_units_kind"), "responder_units", ["kind"])

    op.add_column("case_assignments", sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("case_assignments", sa.Column("route_geojson", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("case_assignments", sa.Column("route_source", sa.Text(), nullable=True))
    op.add_column("case_assignments", sa.Column("distance_m", sa.Integer(), nullable=True))
    op.add_column("case_assignments", sa.Column("eta_minutes", sa.Integer(), nullable=True))
    op.add_column("case_assignments", sa.Column("vehicles", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("case_assignments", sa.Column("notified_via", sa.Text(), nullable=True))
    op.add_column("case_assignments", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("case_assignments", sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_case_assignments_unit_id", "case_assignments", "responder_units", ["unit_id"], ["id"], ondelete="SET NULL")
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
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["responder_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["incident_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vehicle_positions_unit_id"), "vehicle_positions", ["unit_id"])
    op.create_index(op.f("ix_vehicle_positions_case_id"), "vehicle_positions", ["case_id"])
    op.create_index(op.f("ix_vehicle_positions_recorded_at"), "vehicle_positions", ["recorded_at"])
    op.create_index("ix_vehicle_positions_vehicle_time", "vehicle_positions", ["vehicle_id", "recorded_at"])


def downgrade() -> None:
    op.drop_table("vehicle_positions")
    op.drop_index(op.f("ix_case_assignments_unit_id"), table_name="case_assignments")
    op.drop_constraint("fk_case_assignments_unit_id", "case_assignments", type_="foreignkey")
    for col in ("departed_at", "notified_at", "notified_via", "vehicles", "eta_minutes", "distance_m", "route_source", "route_geojson", "unit_id"):
        op.drop_column("case_assignments", col)
    op.drop_table("responder_units")
