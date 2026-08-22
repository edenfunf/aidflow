"""ORM → API dict presenters shared by the console and public routers. The
public presenters are the only path to the public API and apply the privacy
rules; the internal ones add operator-only fields."""
from __future__ import annotations

from app.db.models import CaseEvent, IncidentCase, Report
from app.domain.case_states import PROGRESS_PATH, CaseStatus, next_statuses, phase_of, public_label
from app.domain.categories import category_label
from app.services import privacy_service

_EVENT_LABELS = {
    "report.received": "民眾回報",
    "threshold_reached": "達到案件成立門檻",
    "case.created": "正式成案",
    "status_changed": "狀態更新",
    "public_update": "處理進度",
    "internal_note": "內部備註",
    "assignment_changed": "改派處理單位",
    "dispatch_notified": "已通報處理單位",
}


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
        "lat": case.lat,
        "lon": case.lon,
        "town": case.town,
        "location_label": case.location_label,
        "report_count": case.report_count,
        "unique_reporter_count": case.unique_reporter_count,
        "assigned_unit": case.assigned_unit,
        "public_summary": case.public_summary,
        "threshold_reached_at": case.threshold_reached_at,
        "dispatched_at": case.dispatched_at,
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
        "lat": lat,
        "lon": lon,
        "town": case.town,
        "location_label": case.location_label,
        "report_count": case.report_count,
        "unique_reporter_count": case.unique_reporter_count,
        "assigned_unit": case.assigned_unit,
        "public_summary": privacy_service.redact_text(case.public_summary),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "dispatched_at": case.dispatched_at,
        "resolved_at": case.resolved_at,
    }


def event_item(ev: CaseEvent) -> dict:
    return {
        "id": ev.id,
        "event_type": ev.event_type,
        "from_status": ev.from_status,
        "to_status": ev.to_status,
        "to_status_label": public_label(ev.to_status) if ev.to_status else None,
        "actor_role": ev.actor_role,
        "actor_name": ev.actor_name,
        "note": ev.note,
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
    """Happy-path progress for the public progress bar, derived from real
    events (first time each status was reached)."""
    reached_at: dict[str, object] = {}
    for ev in events:
        if ev.to_status and ev.to_status not in reached_at:
            reached_at[ev.to_status] = ev.created_at
        if ev.event_type == "report.received" and CaseStatus.reported.value not in reached_at:
            reached_at[CaseStatus.reported.value] = ev.created_at
    # statuses implied by later ones
    order = [s.value for s in PROGRESS_PATH]
    current_idx = order.index(case.status) if case.status in order else (
        len(order) - 1 if case.status == CaseStatus.closed.value else None
    )
    if case.status in (CaseStatus.en_route.value,):
        current_idx = order.index(CaseStatus.assigned.value)
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


def report_internal(report: Report) -> dict:
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
        "address": report.address,
        "reporter_role": report.reporter_role,
        "reporter_name": report.reporter_name,
        "reporter_contact": report.reporter_contact,
        "has_identity": report.reporter_key is not None,
        "status": report.status,
        "cluster_id": report.cluster_id,
        "case_id": report.case_id,
        "photo_count": report.photo_count,
        "source": report.source,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }
