"""generated_artifacts and review_tasks

Revision ID: 0002_artifacts
Revises: 0001_initial

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_artifacts"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending_review",
            nullable=False,
        ),
        sa.Column(
            "risk_level",
            sa.Text(),
            server_default="medium",
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Text(),
            server_default="system",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_generated_artifacts_incident_id"),
        "generated_artifacts",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_artifacts_artifact_type"),
        "generated_artifacts",
        ["artifact_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_artifacts_status"),
        "generated_artifacts",
        ["status"],
        unique=False,
    )

    op.create_table(
        "review_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.Text(), nullable=False),
        sa.Column(
            "risk_level",
            sa.Text(),
            server_default="medium",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["generated_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_tasks_incident_id"),
        "review_tasks",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_tasks_artifact_id"),
        "review_tasks",
        ["artifact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_tasks_status"),
        "review_tasks",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_review_tasks_status"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_artifact_id"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_incident_id"), table_name="review_tasks")
    op.drop_table("review_tasks")

    op.drop_index(
        op.f("ix_generated_artifacts_status"), table_name="generated_artifacts"
    )
    op.drop_index(
        op.f("ix_generated_artifacts_artifact_type"),
        table_name="generated_artifacts",
    )
    op.drop_index(
        op.f("ix_generated_artifacts_incident_id"),
        table_name="generated_artifacts",
    )
    op.drop_table("generated_artifacts")
