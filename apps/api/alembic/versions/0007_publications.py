"""publications

Revision ID: 0007_publications
Revises: 0006_assignments

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_publications"
down_revision: Union[str, None] = "0006_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("connector", sa.Text(), server_default="simulated", nullable=False),
        sa.Column("status", sa.Text(), server_default="published", nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["generated_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("incident_id", "artifact_id", "channel", "status", "created_at"):
        op.create_index(
            op.f(f"ix_publications_{col}"), "publications", [col], unique=False
        )


def downgrade() -> None:
    for col in ("created_at", "status", "channel", "artifact_id", "incident_id"):
        op.drop_index(op.f(f"ix_publications_{col}"), table_name="publications")
    op.drop_table("publications")
