"""EMIC 上報連接器.

EMIC has no published API specification yet. Two modes:

  manual — EMIC_SUBMIT_URL unset (default). Nothing is sent; the officer files
           the case in EMIC by hand and records the EMIC case number and status
           in the console. The console says so plainly.
  api    — EMIC_SUBMIT_URL set. The case is POSTed as JSON using the interim
           field map in app/domain/emic.py (Bearer EMIC_API_TOKEN when given).
           A returned ``case_no`` / ``status`` is stored.

No response is ever fabricated: a failure raises ConnectorError and the case
stays reportable by hand.
"""
from __future__ import annotations

import httpx

from app.connectors.base import ConnectorError
from app.core.config import settings
from app.domain.categories import category_label
from app.domain.emic import FIELD_MAP
from app.services import privacy_service


def mode() -> str:
    return "api" if settings.EMIC_SUBMIT_URL else "manual"


def build_payload(platform, case, reports, photo_urls: list[str]) -> dict:
    """``photo_urls`` must already be absolute."""
    values = {
        "source_system": "AidFlow",
        "source_case_no": case.case_number,
        "county": platform.county,
        "town": case.town,
        "location": case.location_label,
        "lat": round(case.lat, 6),
        "lon": round(case.lon, 6),
        "category": case.category,
        "category_label": category_label(case.category),
        "severity": case.severity,
        "occurred_at": case.created_at.isoformat() if case.created_at else None,
        "reported_count": case.report_count,
        "reporter_count": case.unique_reporter_count,
        "description": "\n".join(
            privacy_service.redact_text(r.description) or "" for r in reports if r.description and r.status != "rejected"
        )[:2000],
        "photos": list(photo_urls)[:10],
        "disaster_name": platform.name,
    }
    return {key: values.get(key) for key, _label, _src in FIELD_MAP}


def submit(payload: dict) -> dict:
    """POST to the configured endpoint. Returns {"case_no", "status"} (either
    may be None). Raises ConnectorError on transport / HTTP failure."""
    if not settings.EMIC_SUBMIT_URL:
        raise ConnectorError("EMIC 介接端點未設定（人工登錄模式）")
    headers = {"Content-Type": "application/json"}
    if settings.EMIC_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.EMIC_API_TOKEN}"
    try:
        resp = httpx.post(settings.EMIC_SUBMIT_URL, json=payload, headers=headers,
                          timeout=settings.EMIC_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ConnectorError(f"EMIC 連線失敗：{exc}") from exc
    if resp.status_code >= 400:
        raise ConnectorError(f"EMIC 上報失敗（HTTP {resp.status_code}）：{resp.text[:200]}")
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return {"case_no": body.get("case_no") or body.get("caseNo"), "status": body.get("status")}
