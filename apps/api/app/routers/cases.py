"""Government console — case queue, dispatch and status (protected)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.domain.case_states import InvalidTransitionError
from app.schemas.case import (
    AssignmentItem,
    AssignRequest,
    CaseActionResponse,
    CaseDetailResponse,
    CaseEventItem,
    CaseItem,
    CaseListResponse,
    DispatchNotification,
    DispatchRequest,
    DispatchResponse,
    NearbyCase,
    ResponderSuggestion,
    ResponderSuggestionResponse,
    TransitionRequest,
    UpdateRequest,
)
from app.schemas.report import PhotoItem, ReportInternal
from app.services import (
    case_service,
    cluster_service,
    media_service,
    platform_service,
    presenters,
    report_service,
    responder_service,
)
from app.services.responder_service import UnitNotFoundError

router = APIRouter(prefix="/v1", tags=["cases"])


@router.get("/platforms/{platform_id}/cases", response_model=CaseListResponse, summary="Case queue")
def list_cases(
    platform_id: uuid.UUID,
    phase: str | None = Query(default=None, description="pending | active | done | open"),
    status_filter: str | None = Query(default=None, alias="status", description="comma separated statuses"),
    category: str | None = None,
    town: str | None = None,
    severity: str | None = None,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    sort: str = Query(default="created_desc", description="created_desc | created_asc | severity_desc | reports_desc | updated_desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CaseListResponse:
    if platform_service.get_platform(db, platform_id) is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    rows, total = case_service.list_cases(
        db, platform_id, statuses=[s for s in status_filter.split(",") if s] if status_filter else None,
        phase=phase, category=category, town=town, severity=severity, since=since, sort=sort,
        limit=limit, offset=offset,
    )
    return CaseListResponse(items=[CaseItem(**presenters.case_item(c)) for c in rows], total=total, limit=limit, offset=offset)


def _detail(db: Session, case) -> CaseDetailResponse:
    events = case_service.timeline(db, case.id, public_only=False)
    reports = case_service.reports_of(db, case.id)
    return CaseDetailResponse(
        case=CaseItem(**presenters.case_item(case)),
        reports=[ReportInternal(**presenters.report_internal(r)) for r in reports],
        assignments=[AssignmentItem.model_validate(a) for a in case_service.assignments(db, case.id)],
        events=[CaseEventItem(**presenters.event_item(e)) for e in events],
        photos=[PhotoItem(**media_service.to_item(p)) for p in media_service.photos_for_case(db, case.id, public_only=False)],
        nearby=[NearbyCase(id=c.id, case_number=c.case_number, title=c.title, category=c.category, severity=c.severity,
                           status=c.status, distance_m=round(d)) for c, d in case_service.nearby_cases(db, case)],
        reporter_roles=cluster_service.cluster_reporter_breakdown(db, case.cluster_id) if case.cluster_id else {},
    )


@router.get("/cases/{case_id}", response_model=CaseDetailResponse, summary="Case detail (internal)")
def get_case(case_id: uuid.UUID, db: Session = Depends(get_db)) -> CaseDetailResponse:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return _detail(db, case)


@router.post("/cases/{case_id}/transition", response_model=CaseActionResponse, summary="Move the case along the state machine")
def transition(case_id: uuid.UUID, payload: TransitionRequest, db: Session = Depends(get_db)) -> CaseActionResponse:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        ev = case_service.transition(db, case, payload.status, actor_role="operator", actor_name=payload.actor_name,
                                     note=payload.note, public=payload.public)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "allowed": presenters.next_statuses(case.status)})
    db.commit()
    db.refresh(case)
    return CaseActionResponse(case=CaseItem(**presenters.case_item(case)), event=CaseEventItem(**presenters.event_item(ev)))


@router.post("/cases/{case_id}/assign", response_model=CaseActionResponse, summary="縣府確認並派工")
def assign(case_id: uuid.UUID, payload: AssignRequest, db: Session = Depends(get_db)) -> CaseActionResponse:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status in ("closed", "dismissed"):
        raise HTTPException(status_code=400, detail="已結案或不成案的案件無法派工")
    assignment = case_service.assign(db, case, unit_name=payload.unit_name, team_lead=payload.team_lead,
                                     contact=payload.contact, note=payload.note, actor_name=payload.actor_name)
    db.commit()
    db.refresh(case)
    db.refresh(assignment)
    return CaseActionResponse(case=CaseItem(**presenters.case_item(case)), assignment=AssignmentItem.model_validate(assignment))


@router.get("/cases/{case_id}/responders", response_model=ResponderSuggestionResponse,
            summary="Suggested responder units (category rules → nearest → road route/ETA)")
def responders(case_id: uuid.UUID, db: Session = Depends(get_db)) -> ResponderSuggestionResponse:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    platform = platform_service.require_platform(db, case.platform_id)
    items = responder_service.suggest(db, platform, case)
    return ResponderSuggestionResponse(case_id=case.id, category=case.category, items=[ResponderSuggestion(**i) for i in items])


@router.post("/cases/{case_id}/dispatch", response_model=DispatchResponse,
             summary="通報並派遣：assign a responder unit, route it, notify it")
def dispatch(case_id: uuid.UUID, payload: DispatchRequest, db: Session = Depends(get_db)) -> DispatchResponse:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status in ("closed", "dismissed"):
        raise HTTPException(status_code=400, detail="已結案或不成案的案件無法派遣")
    platform = platform_service.require_platform(db, case.platform_id)
    try:
        assignment, result = responder_service.dispatch(
            db, platform, case, payload.unit_id, note=payload.note, actor_name=payload.actor_name, notify=payload.notify,
        )
    except UnitNotFoundError:
        raise HTTPException(status_code=404, detail="Responder unit not found")
    db.commit()
    db.refresh(case)
    db.refresh(assignment)
    return DispatchResponse(case=CaseItem(**presenters.case_item(case)), assignment=AssignmentItem.model_validate(assignment),
                            notification=DispatchNotification(**result))


@router.post("/cases/{case_id}/updates", response_model=CaseActionResponse, summary="Add a progress note (public or internal)")
def add_update(case_id: uuid.UUID, payload: UpdateRequest, db: Session = Depends(get_db)) -> CaseActionResponse:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    ev = case_service.add_update(db, case, note=payload.note, public=payload.public, actor_name=payload.actor_name)
    db.commit()
    db.refresh(case)
    return CaseActionResponse(case=CaseItem(**presenters.case_item(case)), event=CaseEventItem(**presenters.event_item(ev)))


@router.post("/cases/{case_id}/photos", response_model=PhotoItem, status_code=status.HTTP_201_CREATED,
             summary="Agency photo (before / scene / after)")
async def upload_case_photo(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    kind: str = Form(default="after"),
    caption: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> PhotoItem:
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    data = await file.read()
    try:
        photo = media_service.save_photo(db, platform_id=case.platform_id, data=data, content_type=file.content_type or "",
                                         case=case, kind=kind, source="agency", caption=caption)
    except media_service.MediaTooLargeError:
        raise HTTPException(status_code=413, detail="照片過大")
    except media_service.UnsupportedMediaError:
        raise HTTPException(status_code=415, detail="僅接受 JPEG / PNG / WebP / HEIC")
    return PhotoItem(**media_service.to_item(photo))


# ── reports (internal) ────────────────────────────────────────────────────
@router.get("/reports/{report_id}", summary="Report detail (internal, includes PII)", tags=["reports"])
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    report = report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report": ReportInternal(**presenters.report_internal(report)),
        "photos": [PhotoItem(**media_service.to_item(p)) for p in media_service.photos_for_report(db, report.id)],
    }


@router.post("/reports/{report_id}/reject", response_model=ReportInternal, summary="Mark a report as not credible", tags=["reports"])
def reject_report(report_id: uuid.UUID, note: str | None = None, db: Session = Depends(get_db)) -> ReportInternal:
    report = report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    report = report_service.reject_report(db, report, note=note)
    return ReportInternal(**presenters.report_internal(report))
