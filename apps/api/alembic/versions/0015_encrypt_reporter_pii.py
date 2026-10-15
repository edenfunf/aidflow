"""Encrypt reporters' personal data at rest.

reports.reporter_name / reporter_contact / reporter_email stay TEXT columns;
the application now writes them as AES-GCM ciphertext (app/db/crypto.py).
This migration encrypts the rows written before that. Downgrade decrypts them
again (needs the same DATA_ENCRYPTION_KEY).

Revision ID: 0015_encrypt_reporter_pii
Revises: 0014_review_emic_auth
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db import crypto

revision: str = "0015_encrypt_reporter_pii"
down_revision: Union[str, None] = "0014_review_emic_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("reporter_name", "reporter_contact", "reporter_email")


def _rewrite(fn) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, reporter_name, reporter_contact, reporter_email FROM reports "
            "WHERE reporter_name IS NOT NULL OR reporter_contact IS NOT NULL OR reporter_email IS NOT NULL"
        )
    ).mappings().all()
    for row in rows:
        values = {col: fn(row[col]) for col in _COLUMNS}
        if all(values[col] == row[col] for col in _COLUMNS):
            continue
        conn.execute(
            sa.text(
                "UPDATE reports SET reporter_name = :reporter_name, reporter_contact = :reporter_contact, "
                "reporter_email = :reporter_email WHERE id = :id"
            ),
            {**values, "id": row["id"]},
        )


def upgrade() -> None:
    _rewrite(crypto.encrypt)


def downgrade() -> None:
    _rewrite(crypto.decrypt)
