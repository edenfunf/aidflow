"""disaster_reports

Revision ID: 0003_reports
Revises: 0002_artifacts

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_reports"
down_revision: Union[str, None] = "0002_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "disaster_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reporter_name", sa.Text(), nullable=True),
        sa.Column("reporter_contact", sa.Text(), nullable=True),
        sa.Column("need_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "severity", sa.Text(), server_default="medium", nullable=False
        ),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        sa.Column(
            "verification_status",
            sa.Text(),
            server_default="unverified",
            nullable=False,
        ),
        sa.Column(
            "raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
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
        op.f("ix_disaster_reports_incident_id"),
        "disaster_reports",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_reports_need_type"),
        "disaster_reports",
        ["need_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_reports_severity"),
        "disaster_reports",
        ["severity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_reports_status"),
        "disaster_reports",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_reports_verification_status"),
        "disaster_reports",
        ["verification_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_reports_created_at"),
        "disaster_reports",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_disaster_reports_created_at"), table_name="disaster_reports"
    )
    op.drop_index(
        op.f("ix_disaster_reports_verification_status"),
        table_name="disaster_reports",
    )
    op.drop_index(
        op.f("ix_disaster_reports_status"), table_name="disaster_reports"
    )
    op.drop_index(
        op.f("ix_disaster_reports_severity"), table_name="disaster_reports"
    )
    op.drop_index(
        op.f("ix_disaster_reports_need_type"), table_name="disaster_reports"
    )
    op.drop_index(
        op.f("ix_disaster_reports_incident_id"), table_name="disaster_reports"
    )
    op.drop_table("disaster_reports")
