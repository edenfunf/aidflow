"""Privacy transformation between the internal and the public view
(modules: privacy_mask, personal_data_redaction).

Rules, all deterministic:
  - names, contacts, reporter keys and raw payloads never appear in public output;
  - public coordinates are coarsened to 3 decimals (≈110 m);
  - public addresses keep the road / village level only ("中正路123號" → "中正路一帶");
  - free text has phone numbers / e-mails / national IDs redacted.
"""
from __future__ import annotations

import hashlib
import re

from app.core.config import settings
from app.utils.geo import round_coord

_HOUSE_NO_RE = re.compile(r"\d+(?:[-之]\d+)?\s*號.*$")
_LANE_ALLEY_RE = re.compile(r"\d+\s*[巷弄](?:\d+\s*[巷弄])?")
_FLOOR_RE = re.compile(r"\d+\s*樓.*$")
# Taiwanese mobile / landline numbers with any dash or space grouping
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?886[-\s]?|0)\d(?:[-\s]?\d){7,9}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TW_ID_RE = re.compile(r"\b[A-Z][12]\d{8}\b")
_NAME_HINT_RE = re.compile(r"(我是|聯絡人|連絡人|姓名)[:：]?\s*[一-鿿]{2,4}")


def reporter_key(contact: str | None, client_key: str | None) -> str | None:
    """Opaque identity for unique-reporter counting. Prefers the contact (the
    same person on two devices is still one person), then the device key."""
    basis = (contact or "").strip() or (client_key or "").strip()
    if not basis:
        return None
    digest = hashlib.sha256(f"{settings.REPORTER_HASH_SALT}:{basis}".encode("utf-8")).hexdigest()
    return digest[:32]


def mask_address(address: str | None) -> str | None:
    if not address:
        return None
    text = address.strip()
    original = text
    text = _FLOOR_RE.sub("", text)
    text = _HOUSE_NO_RE.sub("", text)
    text = _LANE_ALLEY_RE.sub("", text)
    text = re.sub(r"[\s,，。]+$", "", text).strip()
    if not text:
        return None
    if text != original and not text.endswith(("一帶", "附近", "路段")):
        text = f"{text}一帶"
    return text


def public_coords(lat: float | None, lon: float | None) -> tuple[float | None, float | None]:
    if lat is None or lon is None:
        return None, None
    return round_coord(lat), round_coord(lon)


def redact_text(text: str | None) -> str | None:
    if not text:
        return text
    out = _EMAIL_RE.sub("[已遮蔽]", text)
    out = _TW_ID_RE.sub("[已遮蔽]", out)
    out = _PHONE_RE.sub("[已遮蔽]", out)
    out = _NAME_HINT_RE.sub(lambda m: m.group(1) + "[已遮蔽]", out)
    return out


def public_report_properties(report) -> dict:
    """Properties safe for the public map / list. No PII, coarse location."""
    lat, lon = public_coords(report.lat, report.lon)
    return {
        "report_id": str(report.id),
        "category": report.category,
        "severity": report.triage_severity,
        "status": report.status,
        "town": report.town,
        "location_label": mask_address(report.address),
        "description": redact_text(report.description),
        "reporter_role": report.reporter_role,
        "photo_count": report.photo_count,
        "case_id": str(report.case_id) if report.case_id else None,
        "cluster_id": str(report.cluster_id) if report.cluster_id else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "lat": lat,
        "lon": lon,
    }
