"""Public Disaster Portal API — everything under /v1/public is reachable
without logging in. Only privacy-transformed data leaves here; writes are rate
limited per client IP."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import IncidentCase, Platform, ReportPhoto
from app.domain.case_states import CaseStatus
from app.schemas.case import CommunitySubmitResponse, PublicCaseDetail, PublicCaseListResponse
from app.schemas.feature import LayerResponse, LayerStatusResponse, MapFeatureCollection
from app.schemas.report import (
    PhotoItem,
    PublicReportListResponse,
    ReportCreate,
    ReportCreateResponse,
)
from app.schemas.situation import SituationResponse
from app.services import (
    case_service,
    cluster_service,
    media_service,
    notification_service,
    official_data_service,
    platform_service,
    presenters,
    privacy_service,
    report_service,
    situation_service,
)
from app.services.case_service import CaseActionError
from app.services.report_service import InvalidCategoryError, PlatformNotAcceptingError
from app.utils import ratelimit

router = APIRouter(prefix="/v1/public", tags=["public"])

_MAX_PHOTOS_PER_REPORT = 5
_MAX_COMMUNITY_PHOTOS = 3
_FINISHED = (CaseStatus.closed.value, CaseStatus.dismissed.value)


def _platform(db: Session, slug: str) -> Platform:
    platform = platform_service.get_by_slug(db, slug, published_only=True)
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return platform


def _media_error(exc: Exception) -> HTTPException:
    if isinstance(exc, media_service.MediaTooLargeError):
        return HTTPException(status_code=413, detail=f"照片需小於 {settings.MEDIA_MAX_BYTES // (1024 * 1024)} MB")
    return HTTPException(status_code=415, detail="僅接受 JPEG / PNG / WebP 照片")


@router.get("/platforms", summary="List published platforms")
def list_platforms(db: Session = Depends(get_db)) -> dict:
    rows, total = platform_service.list_platforms(db, status="published", limit=100)
    return {"items": [platform_service.public_config(p) for p in rows], "total": total}


@router.get("/platforms/{slug}", summary="Public platform configuration")
def get_platform(slug: str, db: Session = Depends(get_db)) -> dict:
    return platform_service.public_config(_platform(db, slug))


@router.get("/platforms/{slug}/situation", response_model=SituationResponse, summary="Live situation picture")
def get_situation(slug: str, db: Session = Depends(get_db)) -> SituationResponse:
    return SituationResponse(**situation_service.situation(db, _platform(db, slug)))


@router.get("/platforms/{slug}/map", response_model=MapFeatureCollection,
            summary="Live cases / clusters / reports (de-identified; closed cases removed)")
def get_map(
    slug: str,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    include_reports: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> MapFeatureCollection:
    platform = _platform(db, slug)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    return MapFeatureCollection(**situation_service.map_collection(
        db, platform, public=True, since=since, include_reports=include_reports
    ))


@router.get("/platforms/{slug}/cases", response_model=PublicCaseListResponse, summary="Public case list")
def list_cases(
    slug: str,
    phase: str | None = Query(default=None, description="pending | active | community | done | open"),
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    town: str | None = None,
    severity: str | None = None,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    sort: str = Query(default="created_desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PublicCaseListResponse:
    platform = _platform(db, slug)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    rows, total = case_service.list_cases(
        db, platform.id, statuses=[status_filter] if status_filter else None, phase=phase, category=category,
        town=town, severity=severity, since=since, public_only=True, sort=sort, limit=limit, offset=offset,
    )
    return PublicCaseListResponse(items=[presenters.public_case(c) for c in rows], total=total)


@router.get("/platforms/{slug}/cases/{case_id}", response_model=PublicCaseDetail, summary="Public case detail + timeline")
def get_case(slug: str, case_id: uuid.UUID, db: Session = Depends(get_db)) -> PublicCaseDetail:
    platform = _platform(db, slug)
    case = case_service.get_case(db, case_id)
    if case is None or case.platform_id != platform.id or case.status == CaseStatus.dismissed.value:
        raise HTTPException(status_code=404, detail="Case not found")
    events = case_service.timeline(db, case.id, public_only=True)
    reports = case_service.reports_of(db, case.id)
    photos = media_service.photos_for_case(db, case.id, public_only=True)
    return PublicCaseDetail(
        case=presenters.public_case(case),
        timeline=[presenters.public_timeline_item(e) for e in events],
        reports=[privacy_service.public_report_properties(r) for r in reports if r.status != "rejected"],
        photos=[PhotoItem(**media_service.to_item(p)) for p in photos],
        progress=presenters.progress(case, events),
        can_assist=case.status == CaseStatus.community_open.value,
    )


@router.post(
    "/platforms/{slug}/cases/{case_id}/community-report",
    response_model=CommunitySubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="民眾回報已協助處理完成（上傳處理完成照片；免登入）",
)
async def community_report(
    slug: str,
    case_id: uuid.UUID,
    request: Request,
    files: list[UploadFile] = File(..., description="處理完成照片，1–3 張"),
    note: str | None = Form(default=None, max_length=500),
    helper_name: str | None = Form(default=None, max_length=60),
    db: Session = Depends(get_db),
) -> CommunitySubmitResponse:
    ratelimit.enforce(request, "community", settings.RATE_LIMIT_REPORTS_PER_MINUTE)
    platform = _platform(db, slug)
    case = case_service.get_case(db, case_id)
    if case is None or case.platform_id != platform.id:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status != CaseStatus.community_open.value:
        raise HTTPException(status_code=409, detail="此案件目前不開放民眾回報處理（可能已有人回報或已結案）")
    photos = [f for f in files if f is not None][:_MAX_COMMUNITY_PHOTOS]
    if not photos:
        raise HTTPException(status_code=422, detail="請至少上傳 1 張處理完成照片")
    # validate every photo before anything is stored
    blobs: list[tuple[bytes, str]] = []
    for f in photos:
        try:
            blobs.append(media_service.prepare(await f.read(), f.content_type))
        except (media_service.MediaTooLargeError, media_service.UnsupportedMediaError) as exc:
            raise _media_error(exc)
    previous = case.status
    try:
        case_service.community_submit(db, case, note=note, helper_name=helper_name, photo_count=len(blobs))
    except CaseActionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    saved = 0
    for data, ctype in blobs:
        try:
            media_service.save_photo(db, platform_id=platform.id, data=data, content_type=ctype, case=case,
                                     kind="after", source="citizen", caption="民眾協助處理完成")
            saved += 1
        except (media_service.MediaTooLargeError, media_service.UnsupportedMediaError):
            continue
    db.refresh(case)
    case_service.after_commit(db, platform, case, previous_status=previous)
    return CommunitySubmitResponse(case=presenters.public_case(case), photos=saved,
                                   message="感謝您協助處理！承辦人員確認照片後會結案，並將此災情自地圖撤除。")


@router.get("/platforms/{slug}/reports", response_model=PublicReportListResponse, summary="Recent reports (de-identified)")
def list_reports(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = None,
    town: str | None = None,
    db: Session = Depends(get_db),
) -> PublicReportListResponse:
    platform = _platform(db, slug)
    rows, total = report_service.list_reports(db, platform.id, category=category, town=town, limit=limit)
    finished = set(db.scalars(select(IncidentCase.id).where(IncidentCase.platform_id == platform.id,
                                                             IncidentCase.status.in_(_FINISHED))).all())
    rows = [r for r in rows if r.status != "rejected" and r.case_id not in finished]
    return PublicReportListResponse(items=[privacy_service.public_report_properties(r) for r in rows], total=total)


@router.post(
    "/platforms/{slug}/reports",
    response_model=ReportCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a disaster report",
)
def submit_report(
    slug: str,
    payload: ReportCreate,
    request: Request,
    x_client_key: str | None = Header(default=None, alias="X-Client-Key"),
    db: Session = Depends(get_db),
) -> ReportCreateResponse:
    ratelimit.enforce(request, "reports", settings.RATE_LIMIT_REPORTS_PER_MINUTE)
    platform = _platform(db, slug)
    try:
        report, cluster, case = report_service.create_report(
            db, platform, payload, client_key=payload.client_key or x_client_key, source="web"
        )
    except PlatformNotAcceptingError:
        raise HTTPException(status_code=400, detail="此平台已封存，不再接受通報")
    except InvalidCategoryError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc), "allowed": exc.allowed})
    policy = cluster_service.policy_for(platform)
    case_id = case.id if case else report.case_id
    case_number = case.case_number if case else None
    if case is None and report.case_id:
        existing = case_service.get_case(db, report.case_id)
        case_number = existing.case_number if existing else None
    if case is not None:
        msg = (f"同一地點已有 {cluster.unique_reporter_count if cluster else policy.required_unique_reporters} 位民眾回報，"
               f"已成案（{case.case_number}），承辦人員正在審核處理方式。")
    elif report.case_id:
        msg = f"此地點已成案（{case_number}），您的回報已併入該案件。"
    elif cluster is not None:
        remaining = max(policy.required_unique_reporters - cluster.unique_reporter_count, 0)
        msg = ("通報已收到，縣府承辦人員會收到通知。"
               + (f"同一地點再有 {remaining} 位民眾回報會自動成案。" if remaining else ""))
    else:
        msg = "通報已收到（未提供位置，承辦人員將另行確認）。"
    if report.notify_opt_in:
        msg += "處理進度會寄到您留下的 Email。"
    return ReportCreateResponse(
        report_id=report.id, status=report.status, cluster_id=report.cluster_id, case_id=case_id,
        case_number=case_number, case_created=case is not None,
        unique_reporters=cluster.unique_reporter_count if cluster else 0,
        required_unique_reporters=policy.required_unique_reporters, notify_opt_in=report.notify_opt_in, message=msg,
    )


@router.post(
    "/reports/{report_id}/photos",
    response_model=PhotoItem,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a scene photo to a freshly submitted report",
)
async def upload_report_photo(
    report_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> PhotoItem:
    ratelimit.enforce(request, "uploads", settings.RATE_LIMIT_UPLOADS_PER_MINUTE)
    report = report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    age = datetime.now(timezone.utc) - report.created_at
    if age > timedelta(hours=24):
        raise HTTPException(status_code=400, detail="此通報已超過可補照片的時間")
    n = db.scalar(select(func.count()).select_from(ReportPhoto).where(ReportPhoto.report_id == report.id)) or 0
    if int(n) >= _MAX_PHOTOS_PER_REPORT:
        raise HTTPException(status_code=400, detail="每筆通報最多 5 張照片")
    data = await file.read()
    try:
        photo = media_service.save_photo(
            db, platform_id=report.platform_id, data=data, content_type=file.content_type or "",
            report=report, kind="scene", source="citizen", caption=caption,
        )
    except (media_service.MediaTooLargeError, media_service.UnsupportedMediaError) as exc:
        raise _media_error(exc)
    return PhotoItem(**media_service.to_item(photo))


@router.post("/unsubscribe", summary="取消案件進度通知（信件中的連結）")
def unsubscribe(request: Request, token: str = Query(..., min_length=10, max_length=100),
                db: Session = Depends(get_db)) -> dict:
    ratelimit.enforce(request, "unsubscribe", settings.RATE_LIMIT_REPORTS_PER_MINUTE)
    report = notification_service.unsubscribe(db, token)
    if report is None:
        raise HTTPException(status_code=404, detail="連結無效或已取消")
    return {"ok": True, "message": "已取消此通報的進度通知。"}


@router.get("/media/{photo_id}", summary="Serve a public photo", include_in_schema=True)
def get_media(photo_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    photo = media_service.get_photo(db, photo_id)
    if photo is None or not photo.public:
        raise HTTPException(status_code=404, detail="Not found")
    path = media_service.path_for(photo)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type=photo.content_type, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/platforms/{slug}/layers", response_model=LayerStatusResponse, summary="Layer availability")
def layer_statuses(slug: str, db: Session = Depends(get_db)) -> LayerStatusResponse:
    return LayerStatusResponse(items=official_data_service.layer_statuses(_platform(db, slug)))


@router.get("/platforms/{slug}/layers/{layer}", response_model=LayerResponse, summary="Official data layer (normalised GeoFeatures)")
def get_layer(request: Request, slug: str, layer: str, db: Session = Depends(get_db)) -> LayerResponse:
    # no "refresh" here on purpose: forcing an upstream fetch is a console action
    # (platforms.py), otherwise anyone could loop us into hammering CWA / 水保署
    ratelimit.enforce(request, "layer", settings.RATE_LIMIT_LAYERS_PER_MINUTE)
    platform = _platform(db, slug)
    return LayerResponse(**official_data_service.get_layer(platform, layer))


@router.get("/radar/{stamp}.{ext}", summary="Cached radar composite frame (proxied from CWA)", include_in_schema=True)
def radar_frame(stamp: str, ext: str) -> Response:
    from app.connectors import cwa

    got = cwa.radar_frame_bytes(stamp)
    if got is None:
        raise HTTPException(status_code=404, detail="frame not cached")
    data, media = got
    # frames are immutable once observed
    return Response(content=data, media_type=media, headers={"Cache-Control": "public, max-age=86400, immutable"})
