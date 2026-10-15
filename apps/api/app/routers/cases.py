"""Government console — review gate, case queue and handling (login required)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.connectors import emic
from app.core.security import Principal, require
from app.db.database import get_db
from app.domain.case_states import InvalidTransitionError, assert_transition
from app.domain.emic import FIELD_MAP, STATUS_SUGGESTIONS
from app.domain.permissions import Perm
from app.schemas.case import (
    CaseActionResponse,
    CaseDetailResponse,
    CaseEventItem,
    CaseItem,
    CaseListResponse,
    CommunityConfirmRequest,
    EmicInfo,
    EmicUpdateRequest,
    NearbyCase,
    ReviewRequest,
    TransitionRequest,
    UpdateRequest,
)
from app.schemas.report import PhotoItem, ReportInternal
from app.services import (
    case_service,
    cluster_service,
    media_service,
    outbox_service,
    platform_service,
    presenters,
    report_service,
)
from app.services.case_service import CaseActionError

router = APIRouter(prefix="/v1", tags=["cases"])


@router.get("/platforms/{platform_id}/cases", response_model=CaseListResponse, summary="Case queue")
def list_cases(
    platform_id: uuid.UUID,
    phase: str | None = Query(default=None, description="pending | active | community | queued | done | open"),
    status_filter: str | None = Query(default=None, alias="status", description="comma separated statuses"),
    track: str | None = Query(default=None, description="emic | community"),
    category: str | None = None,
    town: str | None = None,
    severity: str | None = None,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    sort: str = Query(default="severity_desc", description="severity_desc | created_desc | created_asc | reports_desc | updated_desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Principal = Depends(require(Perm.view_console)),
) -> CaseListResponse:
    if platform_service.get_platform(db, platform_id) is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    rows, total = case_service.list_cases(
        db, platform_id, statuses=[s for s in status_filter.split(",") if s] if status_filter else None,
        phase=phase, track=track, category=category, town=town, severity=severity, since=since, sort=sort,
        limit=limit, offset=offset,
    )
    return CaseListResponse(items=[CaseItem(**presenters.case_item(c)) for c in rows], total=total, limit=limit, offset=offset)


def _require_case(db: Session, case_id: uuid.UUID):
    case = case_service.get_case(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _detail(db: Session, case, principal: Principal) -> CaseDetailResponse:
    events = case_service.timeline(db, case.id, public_only=False)
    reports = case_service.reports_of(db, case.id)
    show_pii = principal.can(Perm.view_pii)
    if show_pii and any(presenters.has_pii(r) for r in reports):
        # 個資查閱留存紀錄
        outbox_service.enqueue_event(db, event_type="pii.viewed", aggregate_id=case.id, payload={
            "platform_id": str(case.platform_id), "case_id": str(case.id), "case_number": case.case_number,
            "user_id": str(principal.user_id) if principal.user_id else None, "username": principal.actor_name,
            "reports": sum(1 for r in reports if presenters.has_pii(r)),
        })
        db.commit()
    return CaseDetailResponse(
        case=CaseItem(**presenters.case_item(case)),
        reports=[ReportInternal(**presenters.report_internal(r, include_pii=show_pii)) for r in reports],
        events=[CaseEventItem(**presenters.event_item(e)) for e in events],
        photos=[PhotoItem(**media_service.to_item(p)) for p in media_service.photos_for_case(db, case.id, public_only=False)],
        nearby=[NearbyCase(id=c.id, case_number=c.case_number, title=c.title, category=c.category, severity=c.severity,
                           status=c.status, distance_m=round(d)) for c, d in case_service.nearby_cases(db, case)],
        reporter_roles=cluster_service.cluster_reporter_breakdown(db, case.cluster_id) if case.cluster_id else {},
        emic=EmicInfo(mode=emic.mode(), field_map=[{"key": k, "label": l, "source": s} for k, l, s in FIELD_MAP],
                      status_suggestions=list(STATUS_SUGGESTIONS)),
        pii_visible=show_pii,
    )


@router.get("/cases/{case_id}", response_model=CaseDetailResponse, summary="Case detail (internal)")
def get_case(case_id: uuid.UUID, db: Session = Depends(get_db),
             principal: Principal = Depends(require(Perm.view_console))) -> CaseDetailResponse:
    return _detail(db, _require_case(db, case_id), principal)


def _respond(db: Session, platform, case, previous: str, ev=None, result: dict | None = None) -> CaseActionResponse:
    db.commit()
    db.refresh(case)
    case_service.after_commit(db, platform, case, previous_status=previous)
    return CaseActionResponse(case=CaseItem(**presenters.case_item(case)),
                              event=CaseEventItem(**presenters.event_item(ev)) if ev is not None else None,
                              result=result)


@router.post("/cases/{case_id}/review", response_model=CaseActionResponse,
             summary="審核點：上報 EMIC／民間可處理／不成案")
def review(case_id: uuid.UUID, payload: ReviewRequest, db: Session = Depends(get_db),
           principal: Principal = Depends(require(Perm.review_cases))) -> CaseActionResponse:
    case = _require_case(db, case_id)
    platform = platform_service.require_platform(db, case.platform_id)
    previous = case.status
    try:
        result = case_service.review(db, platform, case, payload.decision, actor_name=principal.actor_name,
                                     note=payload.note)
    except CaseActionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    return _respond(db, platform, case, previous, result=result)


@router.post("/cases/{case_id}/emic", response_model=CaseActionResponse,
             summary="登錄 EMIC 案號／處理狀態，並可改為處理中或結案")
def update_emic(case_id: uuid.UUID, payload: EmicUpdateRequest, db: Session = Depends(get_db),
                principal: Principal = Depends(require(Perm.review_cases))) -> CaseActionResponse:
    case = _require_case(db, case_id)
    platform = platform_service.require_platform(db, case.platform_id)
    previous = case.status
    try:
        ev = case_service.update_emic(db, case, actor_name=principal.actor_name, emic_case_no=payload.emic_case_no,
                                      emic_status=payload.emic_status, assigned_unit=payload.assigned_unit,
                                      note=payload.note, to_status=payload.status)
    except CaseActionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except InvalidTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"message": str(exc), "allowed": presenters.case_item(case)["next_statuses"]})
    return _respond(db, platform, case, previous, ev)


@router.post("/cases/{case_id}/community/confirm", response_model=CaseActionResponse,
             summary="確認民眾處理完成（通過＝結案並自地圖撤除；不通過＝重新開放）")
def community_confirm(case_id: uuid.UUID, payload: CommunityConfirmRequest, db: Session = Depends(get_db),
                      principal: Principal = Depends(require(Perm.review_cases))) -> CaseActionResponse:
    case = _require_case(db, case_id)
    platform = platform_service.require_platform(db, case.platform_id)
    previous = case.status
    try:
        ev = case_service.community_confirm(db, case, approve=payload.approve, actor_name=principal.actor_name,
                                            note=payload.note)
    except CaseActionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    return _respond(db, platform, case, previous, ev)


@router.post("/cases/{case_id}/transition", response_model=CaseActionResponse, summary="Move the case along the state machine")
def transition(case_id: uuid.UUID, payload: TransitionRequest, db: Session = Depends(get_db),
               principal: Principal = Depends(require(Perm.review_cases))) -> CaseActionResponse:
    case = _require_case(db, case_id)
    platform = platform_service.require_platform(db, case.platform_id)
    previous = case.status
    if payload.status == "reported_emic":
        # escalation from a community case goes through the EMIC path
        try:
            assert_transition(case.status, payload.status)
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc), "allowed": presenters.case_item(case)["next_statuses"]})
        result = case_service.report_to_emic(db, platform, case, actor_name=principal.actor_name,
                                             note=payload.note or "改列上報 EMIC")
        return _respond(db, platform, case, previous, result=result)
    try:
        ev = case_service.transition(db, case, payload.status, actor_role="operator", actor_name=principal.actor_name,
                                     note=payload.note, public=payload.public)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "allowed": presenters.case_item(case)["next_statuses"]})
    return _respond(db, platform, case, previous, ev)


@router.post("/cases/{case_id}/updates", response_model=CaseActionResponse, summary="Add a progress note (public or internal)")
def add_update(case_id: uuid.UUID, payload: UpdateRequest, db: Session = Depends(get_db),
               principal: Principal = Depends(require(Perm.review_cases))) -> CaseActionResponse:
    case = _require_case(db, case_id)
    ev = case_service.add_update(db, case, note=payload.note, public=payload.public, actor_name=principal.actor_name)
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
    _: Principal = Depends(require(Perm.review_cases)),
) -> PhotoItem:
    case = _require_case(db, case_id)
    data = await file.read()
    try:
        photo = media_service.save_photo(db, platform_id=case.platform_id, data=data, content_type=file.content_type or "",
                                         case=case, kind=kind, source="agency", caption=caption)
    except media_service.MediaTooLargeError:
        raise HTTPException(status_code=413, detail="照片過大")
    except media_service.UnsupportedMediaError:
        raise HTTPException(status_code=415, detail="僅接受 JPEG / PNG / WebP 照片")
    return PhotoItem(**media_service.to_item(photo))


# ── reports (internal) ────────────────────────────────────────────────────
@router.get("/reports/{report_id}", summary="Report detail (internal; PII for view_pii roles)", tags=["reports"])
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db),
               principal: Principal = Depends(require(Perm.view_console))) -> dict:
    report = report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    show_pii = principal.can(Perm.view_pii)
    if show_pii and presenters.has_pii(report):
        outbox_service.enqueue_event(db, event_type="pii.viewed", aggregate_id=report.id, payload={
            "platform_id": str(report.platform_id), "report_id": str(report.id),
            "user_id": str(principal.user_id) if principal.user_id else None, "username": principal.actor_name,
        })
        db.commit()
    return {
        "report": ReportInternal(**presenters.report_internal(report, include_pii=show_pii)),
        "photos": [PhotoItem(**media_service.to_item(p)) for p in media_service.photos_for_report(db, report.id)],
    }


@router.post("/reports/{report_id}/reject", response_model=ReportInternal, summary="Mark a report as not credible", tags=["reports"])
def reject_report(report_id: uuid.UUID, note: str | None = None, db: Session = Depends(get_db),
                  principal: Principal = Depends(require(Perm.review_cases))) -> ReportInternal:
    report = report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    report = report_service.reject_report(db, report, note=note)
    return ReportInternal(**presenters.report_internal(report, include_pii=principal.can(Perm.view_pii)))
