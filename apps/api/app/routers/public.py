"""Public Disaster Portal API — everything under /v1/public is reachable
without the API key. Only privacy-transformed data leaves here."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Response, APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Platform, Report, ReportPhoto
from app.domain.case_states import CaseStatus
from app.schemas.case import PublicCaseDetail, PublicCaseListResponse
from app.schemas.feature import LayerResponse, LayerStatusResponse, MapFeatureCollection, VehicleItem, VehicleListResponse
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
    official_data_service,
    platform_service,
    presenters,
    privacy_service,
    report_service,
    responder_service,
    situation_service,
)
from app.services.report_service import InvalidCategoryError, PlatformNotAcceptingError

router = APIRouter(prefix="/v1/public", tags=["public"])


def _platform(db: Session, slug: str) -> Platform:
    platform = platform_service.get_by_slug(db, slug, published_only=True)
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return platform


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


@router.get("/platforms/{slug}/map", response_model=MapFeatureCollection, summary="Cases / clusters / reports (de-identified)")
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
    phase: str | None = Query(default=None, description="pending | active | done | open"),
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
    )


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
    rows = [r for r in rows if r.status != "rejected"]
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
    x_client_key: str | None = Header(default=None, alias="X-Client-Key"),
    db: Session = Depends(get_db),
) -> ReportCreateResponse:
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
        msg = f"已有 {cluster.unique_reporter_count if cluster else policy.required_unique_reporters} 位不同回報者回報同一地點，已自動成案（{case.case_number}），進入政府待派工。"
    elif report.case_id:
        msg = f"此地點已成案（{case_number}），您的回報已併入該案件。"
    elif cluster is not None:
        remaining = max(policy.required_unique_reporters - cluster.unique_reporter_count, 0)
        msg = f"通報已收到。目前 {cluster.unique_reporter_count} 位回報者，再 {remaining} 位不同回報者確認即自動成案。" if remaining else "通報已收到。"
    else:
        msg = "通報已收到（未提供座標，不參與同地點聚類）。"
    return ReportCreateResponse(
        report_id=report.id, status=report.status, cluster_id=report.cluster_id, case_id=case_id,
        case_number=case_number, case_created=case is not None,
        unique_reporters=cluster.unique_reporter_count if cluster else 0,
        required_unique_reporters=policy.required_unique_reporters, message=msg,
    )


_MAX_PHOTOS_PER_REPORT = 5


@router.post(
    "/reports/{report_id}/photos",
    response_model=PhotoItem,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a scene photo to a freshly submitted report",
)
async def upload_report_photo(
    report_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> PhotoItem:
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
    except media_service.MediaTooLargeError:
        raise HTTPException(status_code=413, detail=f"照片需小於 {settings.MEDIA_MAX_BYTES // (1024 * 1024)} MB")
    except media_service.UnsupportedMediaError:
        raise HTTPException(status_code=415, detail="僅接受 JPEG / PNG / WebP / HEIC")
    return PhotoItem(**media_service.to_item(photo))


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
def get_layer(slug: str, layer: str, refresh: bool = False, db: Session = Depends(get_db)) -> LayerResponse:
    platform = _platform(db, slug)
    return LayerResponse(**official_data_service.get_layer(platform, layer, force=refresh))


@router.get("/radar/{stamp}.{ext}", summary="Cached radar composite frame (proxied from CWA)", include_in_schema=True)
def radar_frame(stamp: str, ext: str) -> Response:
    from app.connectors import cwa

    got = cwa.radar_frame_bytes(stamp)
    if got is None:
        raise HTTPException(status_code=404, detail="frame not cached")
    data, media = got
    # frames are immutable once observed
    return Response(content=data, media_type=media, headers={"Cache-Control": "public, max-age=86400, immutable"})


@router.get("/platforms/{slug}/vehicles", response_model=VehicleListResponse, summary="Responding vehicles (AVL if available, else labelled simulation)")
def vehicles(slug: str, db: Session = Depends(get_db),
             elapsed: float | None = Query(None, ge=0, le=86_400, description="示範平台專用：此瀏覽器開啟頁面已經過的秒數。每次載入從 0 開始，車輛就會從駐地重新出發，而不是停在早已抵達的位置。不影響 AVL 實車資料與案件狀態。")) -> VehicleListResponse:
    platform = _platform(db, slug)
    items = responder_service.vehicles(db, platform, public=True, elapsed_s=elapsed)
    return VehicleListResponse(items=[VehicleItem(**v) for v in items], generated_at=datetime.now(timezone.utc).isoformat(),
                               has_live=any(v["source"] == "avl" for v in items))


@router.get("/platforms/{slug}/routes", response_model=MapFeatureCollection, summary="Active dispatch routes (real road geometry)")
def routes(slug: str, db: Session = Depends(get_db)) -> MapFeatureCollection:
    return MapFeatureCollection(**responder_service.routes(db, _platform(db, slug), public=True))
