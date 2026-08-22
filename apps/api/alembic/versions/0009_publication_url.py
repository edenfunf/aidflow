"""publication url

Revision ID: 0009_publication_url
Revises: 0008_form_submissions

Adds a nullable ``url`` column to publications so a real connector can store a
clickable link to the published post / created form (simulated rows leave it
null).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_publication_url"
down_revision: Union[str, None] = "0008_form_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("publications", "url")
