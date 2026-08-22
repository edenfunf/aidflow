from __future__ import annotations

import re
import unicodedata
import uuid

_SEP_RE = re.compile(r"[\s_/\\]+")
# keep word chars (incl. CJK) and hyphens, drop the rest
_DROP_RE = re.compile(r"[^\w\-]+", flags=re.UNICODE)
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def slugify(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = _SEP_RE.sub("-", value)
    value = _DROP_RE.sub("", value)
    value = _MULTI_HYPHEN_RE.sub("-", value).strip("-")
    return value or "incident"


def short_suffix() -> str:
    return uuid.uuid4().hex[:8]
