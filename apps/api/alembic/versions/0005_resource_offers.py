"""resource_offers

Revision ID: 0005_resource_offers
Revises: 0004_report_triage

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_resource_offers"
down_revision: Union[str, None] = "0004_report_triage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        op.f("ix_resource_offers_incident_id"),
        "resource_offers",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resource_offers_offer_type"),
        "resource_offers",
        ["offer_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resource_offers_status"),
        "resource_offers",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resource_offers_created_at"),
        "resource_offers",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_resource_offers_created_at"), table_name="resource_offers")
    op.drop_index(op.f("ix_resource_offers_status"), table_name="resource_offers")
    op.drop_index(op.f("ix_resource_offers_offer_type"), table_name="resource_offers")
    op.drop_index(op.f("ix_resource_offers_incident_id"), table_name="resource_offers")
    op.drop_table("resource_offers")
