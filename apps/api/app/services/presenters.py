"""ORM → API dict presenters shared by the console and public routers. The
public presenters are the only path to the public API and apply the privacy
rules; the internal ones add operator-only fields, and personal data only for
roles holding ``view_pii``."""
from __future__ import annotations

from app.db.models import CaseEvent, IncidentCase, Report
from app.domain.case_states import PROGRESS_PATHS, CaseStatus, next_statuses, phase_of, public_label, track_of
from app.domain.categories import category_label
from app.services import privacy_service

_EVENT_LABELS = {
    "report.received": "民眾回報",
    "threshold_reached": "達到多人回報門檻",
    "case.created": "成案",
    "status_changed": "狀態更新",
    "public_update": "處理進度",
    "internal_note": "內部備註",
    "emic_updated": "EMIC 資訊更新",
    "emic_submitted": "已上報 EMIC",
    "emic_submit_failed": "EMIC 自動上報失敗",
}

TRACK_LABELS = {"emic": "上報 EMIC", "community": "民間可處理"}


def event_label(ev: CaseEvent) -> str:
    if ev.event_type == "status_changed" and ev.to_status:
        return public_label(ev.to_status)
    return _EVENT_LABELS.get(ev.event_type, ev.event_type)


def case_item(case: IncidentCase) -> dict:
    return {
        "id": case.id,
        "platform_id": case.platform_id,
        "cluster_id": case.cluster_id,
        "case_number": case.case_number,
        "title": case.title,
        "category": case.category,
        "category_label": category_label(case.category),
        "severity": case.severity,
        "status": case.status,
        "status_label": public_label(case.status),
        "phase": phase_of(case.status),
        "track": case.track,
        "track_label": TRACK_LABELS.get(case.track or ""),
        "lat": case.lat,
        "lon": case.lon,
        "town": case.town,
        "location_label": case.location_label,
        "report_count": case.report_count,
        "unique_reporter_count": case.unique_reporter_count,
        "assigned_unit": case.assigned_unit,
        "public_summary": case.public_summary,
        "reviewed_by": case.reviewed_by,
        "reviewed_at": case.reviewed_at,
        "emic_case_no": case.emic_case_no,
        "emic_status": case.emic_status,
        "emic_channel": case.emic_channel,
        "emic_reported_at": case.emic_reported_at,
        "emic_synced_at": case.emic_synced_at,
        "community_submitted_at": case.community_submitted_at,
        "threshold_reached_at": case.threshold_reached_at,
        "resolved_at": case.resolved_at,
        "closed_at": case.closed_at,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "next_statuses": next_statuses(case.status),
    }


def public_case(case: IncidentCase) -> dict:
    lat, lon = privacy_service.public_coords(case.lat, case.lon)
    return {
        "id": case.id,
        "case_number": case.case_number,
        "title": case.title,
        "category": case.category,
        "category_label": category_label(case.category),
        "severity": case.severity,
        "status": case.status,
        "status_label": public_label(case.status),
        "phase": phase_of(case.status),
        "track": case.track,
        "track_label": TRACK_LABELS.get(case.track or ""),
        "lat": lat,
        "lon": lon,
        "town": case.town,
        "location_label": case.location_label,
        "report_count": case.report_count,
        "unique_reporter_count": case.unique_reporter_count,
        "assigned_unit": case.assigned_unit,
        # the EMIC status text is public progress; the EMIC case number is not
        "emic_status": case.emic_status,
        "public_summary": privacy_service.redact_text(case.public_summary),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "reviewed_at": case.reviewed_at,
        "closed_at": case.closed_at,
    }


def event_item(ev: CaseEvent) -> dict:
    internal = (ev.payload or {}).get("internal_note")
    return {
        "id": ev.id,
        "event_type": ev.event_type,
        "label": event_label(ev),
        "from_status": ev.from_status,
        "to_status": ev.to_status,
        "to_status_label": public_label(ev.to_status) if ev.to_status else None,
        "actor_role": ev.actor_role,
        "actor_name": ev.actor_name,
        "note": internal or ev.note,
        "public": ev.public,
        "created_at": ev.created_at,
    }


def public_timeline_item(ev: CaseEvent) -> dict:
    return {
        "event_type": ev.event_type,
        "label": event_label(ev),
        "note": privacy_service.redact_text(ev.note),
        "to_status": ev.to_status,
        "at": ev.created_at,
    }


def progress(case: IncidentCase, events: list[CaseEvent]) -> list[dict]:
    """Progress along the case's own track, derived from real events (first
    time each status was reached)."""
    reached_at: dict[str, object] = {}
    for ev in events:
        if ev.to_status and ev.to_status not in reached_at:
            reached_at[ev.to_status] = ev.created_at
    track = case.track or track_of(case.status)
    if case.status == CaseStatus.dismissed.value:
        path = (CaseStatus.pending_review, CaseStatus.dismissed)
    else:
        path = PROGRESS_PATHS.get(track, PROGRESS_PATHS[None])
    order = [s.value for s in path]
    current_idx = order.index(case.status) if case.status in order else None
    out = []
    for i, key in enumerate(order):
        reached = key in reached_at or (current_idx is not None and i <= current_idx)
        out.append({
            "key": key,
            "label": public_label(key),
            "reached": reached,
            "current": current_idx == i,
            "at": reached_at.get(key),
        })
    return out


def report_internal(report: Report, *, include_pii: bool) -> dict:
    return {
        "id": report.id,
        "platform_id": report.platform_id,
        "category": report.category,
        "description": report.description,
        "severity": report.severity,
        "triage_severity": report.triage_severity,
        "lat": report.lat,
        "lon": report.lon,
        "town": report.town,
        "address": report.address if include_pii else privacy_service.mask_address(report.address),
        "reporter_role": report.reporter_role,
        "reporter_name": report.reporter_name if include_pii else None,
        "reporter_contact": report.reporter_contact if include_pii else None,
        "reporter_email": report.reporter_email if include_pii else None,
        "pii_hidden": not include_pii and bool(report.reporter_name or report.reporter_contact or report.reporter_email),
        "notify_opt_in": report.notify_opt_in,
        "has_identity": report.reporter_key is not None,
        "status": report.status,
        "cluster_id": report.cluster_id,
        "case_id": report.case_id,
        "photo_count": report.photo_count,
        "source": report.source,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def has_pii(report: Report) -> bool:
    return bool(report.reporter_name or report.reporter_contact or report.reporter_email)
