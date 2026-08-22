"""assignments

Revision ID: 0006_assignments
Revises: 0005_resource_offers

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_assignments"
down_revision: Union[str, None] = "0005_resource_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="assigned", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_id"], ["disaster_reports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"], ["resource_offers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "report_id", "offer_id", "status", "created_at"):
        op.create_index(
            op.f(f"ix_assignments_{col}"), "assignments", [col], unique=False
        )


def downgrade() -> None:
    for col in ("created_at", "status", "offer_id", "report_id", "incident_id"):
        op.drop_index(op.f(f"ix_assignments_{col}"), table_name="assignments")
    op.drop_table("assignments")
