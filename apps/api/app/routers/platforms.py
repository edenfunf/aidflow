"""Government console — platform management (protected by the API key gate)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Platform
from app.schemas.case import CaseItem
from app.schemas.feature import LayerResponse, LayerStatusResponse, MapFeatureCollection, VehicleItem, VehicleListResponse
from app.schemas.platform import (
    ModuleConfigItem,
    PlatformConfigUpdate,
    PlatformCreate,
    PlatformDetail,
    PlatformItem,
    PlatformListResponse,
    PlatformStatusUpdate,
)
from app.schemas.report import ReportInternal, ReportListResponse
from app.schemas.situation import ConsoleOverviewResponse
from app.services import (
    case_service,
    cluster_service,
    official_data_service,
    outbox_service,
    platform_service,
    presenters,
    report_service,
    responder_service,
    situation_service,
)
from app.services.platform_service import InvalidSelectionError

router = APIRouter(prefix="/v1/platforms", tags=["platforms"])


def _require(db: Session, platform_id: uuid.UUID) -> Platform:
    p = platform_service.get_platform(db, platform_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return p


def detail(db: Session, platform: Platform) -> PlatformDetail:
    base = settings.WEB_PUBLIC_BASE_URL.rstrip("/")
    return PlatformDetail(
        **{c.name: getattr(platform, c.name) for c in Platform.__table__.columns},
        module_configs=[ModuleConfigItem.model_validate(m) for m in platform_service.module_configs(db, platform.id)],
        public_url=f"{base}/p/{platform.slug}",
        console_url=f"{base}/console/platforms/{platform.id}",
    )


@router.get("", response_model=PlatformListResponse, summary="List platforms")
def list_platforms(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PlatformListResponse:
    rows, total = platform_service.list_platforms(db, status=status_filter, limit=limit, offset=offset)
    return PlatformListResponse(items=[PlatformItem.model_validate(p) for p in rows], total=total)


@router.post("", response_model=PlatformDetail, status_code=status.HTTP_201_CREATED, summary="Compose a platform directly")
def create_platform(payload: PlatformCreate, db: Session = Depends(get_db)) -> PlatformDetail:
    try:
        platform = platform_service.create_platform(
            db, name=payload.name, brief=payload.brief, hazards=payload.hazards, county=payload.county,
            towns=payload.towns, modules=payload.modules, layers=payload.layers,
            report_categories=payload.report_categories,
            cluster_policy=payload.cluster_policy.model_dump() if payload.cluster_policy else None,
            configuration=payload.configuration, publish=payload.publish, source="console", slug=payload.slug,
        )
    except InvalidSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return detail(db, platform)


@router.get("/{platform_id}", response_model=PlatformDetail, summary="Platform detail")
def get_platform(platform_id: uuid.UUID, db: Session = Depends(get_db)) -> PlatformDetail:
    return detail(db, _require(db, platform_id))


@router.post("/{platform_id}/status", response_model=PlatformDetail, summary="Publish / unpublish / archive")
def set_status(platform_id: uuid.UUID, payload: PlatformStatusUpdate, db: Session = Depends(get_db)) -> PlatformDetail:
    try:
        platform = platform_service.set_status(db, _require(db, platform_id), payload.status)
    except InvalidSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return detail(db, platform)


@router.patch("/{platform_id}", response_model=PlatformDetail, summary="Update name / cluster policy / configuration")
def update_platform(platform_id: uuid.UUID, payload: PlatformConfigUpdate, db: Session = Depends(get_db)) -> PlatformDetail:
    platform = platform_service.update_configuration(
        db, _require(db, platform_id), name=payload.name,
        cluster_policy=payload.cluster_policy.model_dump() if payload.cluster_policy else None,
        configuration=payload.configuration,
    )
    return detail(db, platform)


@router.get("/{platform_id}/overview", response_model=ConsoleOverviewResponse, summary="Command-centre overview")
def overview(platform_id: uuid.UUID, db: Session = Depends(get_db)) -> ConsoleOverviewResponse:
    return ConsoleOverviewResponse(**situation_service.console_overview(db, _require(db, platform_id)))


@router.get("/{platform_id}/map", response_model=MapFeatureCollection, summary="Internal map (precise coordinates)")
def internal_map(
    platform_id: uuid.UUID,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    include_reports: bool = True,
    db: Session = Depends(get_db),
) -> MapFeatureCollection:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    return MapFeatureCollection(**situation_service.map_collection(
        db, _require(db, platform_id), public=False, since=since, include_reports=include_reports
    ))


@router.get("/{platform_id}/reports", response_model=ReportListResponse, summary="Internal report list (includes PII)")
def list_reports(
    platform_id: uuid.UUID,
    category: str | None = None,
    town: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    _require(db, platform_id)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    rows, total = report_service.list_reports(
        db, platform_id, category=category, town=town, status=status_filter, severity=severity, since=since,
        limit=limit, offset=offset,
    )
    return ReportListResponse(items=[ReportInternal(**presenters.report_internal(r)) for r in rows],
                              total=total, limit=limit, offset=offset)


@router.get("/{platform_id}/clusters", summary="Report clusters (open ones are candidates for manual promotion)")
def list_clusters(platform_id: uuid.UUID, status_filter: str | None = Query(default=None, alias="status"),
                  db: Session = Depends(get_db)) -> dict:
    _require(db, platform_id)
    rows = cluster_service.list_clusters(db, platform_id, status=status_filter)
    return {"items": [situation_service.cluster_feature(c, public=False)["properties"] | {
        "lat": c.centroid_lat, "lon": c.centroid_lon} for c in rows], "total": len(rows)}


@router.post("/{platform_id}/clusters/{cluster_id}/promote", response_model=CaseItem,
             summary="Manually create a case from a cluster below threshold")
def promote_cluster(platform_id: uuid.UUID, cluster_id: uuid.UUID, actor_name: str | None = None,
                    db: Session = Depends(get_db)) -> CaseItem:
    platform = _require(db, platform_id)
    cluster = next((c for c in cluster_service.list_clusters(db, platform_id, limit=10000) if c.id == cluster_id), None)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    case = case_service.promote_cluster(db, platform, cluster, actor_name=actor_name)
    db.commit()
    db.refresh(case)
    return CaseItem(**presenters.case_item(case))


@router.get("/{platform_id}/layers", response_model=LayerStatusResponse, summary="Layer availability")
def layer_statuses(platform_id: uuid.UUID, db: Session = Depends(get_db)) -> LayerStatusResponse:
    return LayerStatusResponse(items=official_data_service.layer_statuses(_require(db, platform_id)))


@router.get("/{platform_id}/layers/{layer}", response_model=LayerResponse, summary="Official data layer")
def get_layer(platform_id: uuid.UUID, layer: str, refresh: bool = False, db: Session = Depends(get_db)) -> LayerResponse:
    return LayerResponse(**official_data_service.get_layer(_require(db, platform_id), layer, force=refresh))


@router.get("/{platform_id}/audit", summary="Audit trail (event outbox) for this platform")
def audit(platform_id: uuid.UUID, limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0),
          db: Session = Depends(get_db)) -> dict:
    _require(db, platform_id)
    rows = outbox_service.list_platform_events(db, platform_id, limit=limit, offset=offset)
    return {"items": [{"id": str(e.id), "event_type": e.event_type, "aggregate_id": str(e.aggregate_id) if e.aggregate_id else None,
                       "payload": e.payload, "created_at": e.created_at.isoformat()} for e in rows]}


@router.get("/{platform_id}/vehicles", response_model=VehicleListResponse, summary="Responding vehicles (precise)")
def vehicles(platform_id: uuid.UUID, db: Session = Depends(get_db)) -> VehicleListResponse:
    items = responder_service.vehicles(db, _require(db, platform_id), public=False)
    return VehicleListResponse(items=[VehicleItem(**v) for v in items], generated_at=datetime.now(timezone.utc).isoformat(),
                               has_live=any(v["source"] == "avl" for v in items))


@router.get("/{platform_id}/routes", response_model=MapFeatureCollection, summary="Active dispatch routes")
def routes(platform_id: uuid.UUID, db: Session = Depends(get_db)) -> MapFeatureCollection:
    return MapFeatureCollection(**responder_service.routes(db, _require(db, platform_id), public=False))


@router.get("/{platform_id}/units", summary="Responder unit registry for this platform's county")
def units(platform_id: uuid.UUID, refresh: bool = False, db: Session = Depends(get_db)) -> dict:
    rows = responder_service.ensure_units(db, _require(db, platform_id), refresh=refresh)
    return {"items": [responder_service.unit_dict(u) | {"id": str(u.id)} for u in rows], "total": len(rows)}
