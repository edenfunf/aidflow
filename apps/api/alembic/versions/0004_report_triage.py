"""add triage_priority to disaster_reports

Revision ID: 0004_report_triage
Revises: 0003_reports

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_report_triage"
down_revision: Union[str, None] = "0003_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "disaster_reports",
        sa.Column(
            "triage_priority",
            sa.Text(),
            server_default="normal",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_disaster_reports_triage_priority"),
        "disaster_reports",
        ["triage_priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_disaster_reports_triage_priority"),
        table_name="disaster_reports",
    )
    op.drop_column("disaster_reports", "triage_priority")
