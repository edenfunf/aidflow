"""form_submissions

Revision ID: 0008_form_submissions
Revises: 0007_publications

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_form_submissions"
down_revision: Union[str, None] = "0007_publications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "form_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("form_key", sa.Text(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
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
    for col in ("incident_id", "artifact_id", "form_key", "created_at"):
        op.create_index(
            op.f(f"ix_form_submissions_{col}"), "form_submissions", [col], unique=False
        )


def downgrade() -> None:
    for col in ("created_at", "form_key", "artifact_id", "incident_id"):
        op.drop_index(op.f(f"ix_form_submissions_{col}"), table_name="form_submissions")
    op.drop_table("form_submissions")
