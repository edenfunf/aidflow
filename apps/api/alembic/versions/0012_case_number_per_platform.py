"""Case numbers are unique per platform, not globally.

Two platforms in the same county derive the same human-readable prefix
(NT-20260821-0001), so uniqueness must be scoped to the platform.

Revision ID: 0012_case_number_per_platform
Revises: 0011_retire_resqlink_tables
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_case_number_per_platform"
down_revision: Union[str, None] = "0011_retire_resqlink_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_incident_cases_case_number", "incident_cases", type_="unique")
    op.create_unique_constraint(
        "uq_incident_cases_platform_case_number", "incident_cases", ["platform_id", "case_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_incident_cases_platform_case_number", "incident_cases", type_="unique")
    op.create_unique_constraint("uq_incident_cases_case_number", "incident_cases", ["case_number"])
