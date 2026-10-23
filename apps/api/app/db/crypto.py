"""Field-level encryption for reporters' personal data (聯絡資料加密保存).

Values are stored as ``enc:v1:<base64(nonce ‖ AES-256-GCM ciphertext)>``.
The key is ``DATA_ENCRYPTION_KEY`` (32 random bytes as URL-safe base64, or
any long random string, which is hashed to 32 bytes). It is required outside
development — a deployment without it refuses to start (see
``settings.startup_problems``) rather than silently using a guessable key.
In development a per-process random key is generated, so values written
without a configured key cannot be read back after a restart.

Values written before encryption was introduced (no prefix) are returned as
they are, and re-encrypted by migration 0015.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

logger = logging.getLogger("aidflow.crypto")

PREFIX = "enc:v1:"
UNREADABLE = "[無法解密]"


# development-only fallback: random per process, never a value from the repo
_EPHEMERAL_KEY = os.urandom(32)


def _key() -> bytes:
    raw = settings.DATA_ENCRYPTION_KEY.strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            if len(key) == 32:
                return key
        except ValueError:
            pass  # not base64 — fall through and hash the string instead
        # any other long random string (e.g. openssl rand -hex 32) is hashed to 32 bytes
        return hashlib.sha256(raw.encode("utf-8")).digest()
    if not settings.is_development:
        raise RuntimeError("DATA_ENCRYPTION_KEY 未設定：無法加密通報者聯絡資料")
    return _EPHEMERAL_KEY


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(PREFIX))


def encrypt(value: str | None) -> str | None:
    if value is None or value == "" or is_encrypted(value):
        return value
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, value.encode("utf-8"), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(value: str | None) -> str | None:
    if not is_encrypted(value):
        return value
    try:
        blob = base64.urlsafe_b64decode(value[len(PREFIX):].encode("ascii"))
        return AESGCM(_key()).decrypt(blob[:12], blob[12:], None).decode("utf-8")
    except (InvalidTag, ValueError) as exc:
        logger.warning("cannot decrypt a personal-data field (wrong DATA_ENCRYPTION_KEY?): %s", exc)
        return UNREADABLE


class EncryptedText(TypeDecorator):
    """A Text column encrypted at rest; application code sees plaintext."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)
