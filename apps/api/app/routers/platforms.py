"""Government console — platform management (login required)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import Principal, require
from app.db.database import get_db
from app.db.models import Platform
from app.domain.permissions import Perm
from app.schemas.case import CaseItem
from app.schemas.feature import LayerResponse, LayerStatusResponse, MapFeatureCollection
from app.schemas.platform import (
    ModuleConfigItem,
    PlatformConfigUpdate,
    PlatformCreate,
    PlatformDetail,
    PlatformItem,
    PlatformListResponse,
    PlatformPreviewRequest,
    PlatformStatusUpdate,
)
from app.schemas.report import ReportInternal, ReportListResponse
from app.schemas.situation import ConsoleOverviewResponse
from app.services import (
    case_service,
    cluster_service,
    line_service,
    notification_service,
    official_data_service,
    outbox_service,
    platform_service,
    presenters,
    report_service,
    situation_service,
)
from app.services.platform_service import InvalidSelectionError

router = APIRouter(prefix="/v1/platforms", tags=["platforms"])

# case / report pipeline events for the live feed (security events live in /v1/admin/audit)
_FEED_EXCLUDE = ("auth.", "user.", "pii.")


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
        embed_url=f"{base}/embed/{platform.slug}",
    )


@router.get("", response_model=PlatformListResponse, summary="List platforms")
def list_platforms(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Principal = Depends(require(Perm.view_console)),
) -> PlatformListResponse:
    rows, total = platform_service.list_platforms(db, status=status_filter, limit=limit, offset=offset)
    return PlatformListResponse(items=[PlatformItem.model_validate(p) for p in rows], total=total)


@router.get("/options", summary="災害類型與縣市鄉鎮選項（建立平台用）")
def options(_: Principal = Depends(require(Perm.view_console))) -> dict:
    return {"hazards": platform_service.hazard_options(), "regions": platform_service.region_options()}


@router.post("/preview", summary="依災害名稱與類型預覽平台內容（不寫入）")
def preview(payload: PlatformPreviewRequest, _: Principal = Depends(require(Perm.manage_platforms))) -> dict:
    return platform_service.preview(name=payload.name, hazards=payload.hazards, county=payload.county, towns=payload.towns)


@router.post("", response_model=PlatformDetail, status_code=status.HTTP_201_CREATED, summary="建立災害平台")
def create_platform(payload: PlatformCreate, db: Session = Depends(get_db),
                    principal: Principal = Depends(require(Perm.manage_platforms))) -> PlatformDetail:
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
    outbox_service.enqueue_event(db, event_type="platform.created_by", aggregate_id=platform.id,
                                 payload={"platform_id": str(platform.id), "by": principal.actor_name})
    db.commit()
    platform_service.prune_generated(db, protect={platform.id})
    return detail(db, platform)


@router.get("/{platform_id}", response_model=PlatformDetail, summary="Platform detail")
def get_platform(platform_id: uuid.UUID, db: Session = Depends(get_db),
                 _: Principal = Depends(require(Perm.view_console))) -> PlatformDetail:
    return detail(db, _require(db, platform_id))


@router.post("/{platform_id}/status", response_model=PlatformDetail, summary="Publish / unpublish / archive")
def set_status(platform_id: uuid.UUID, payload: PlatformStatusUpdate, db: Session = Depends(get_db),
               _: Principal = Depends(require(Perm.manage_platforms))) -> PlatformDetail:
    try:
        platform = platform_service.set_status(db, _require(db, platform_id), payload.status)
    except InvalidSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return detail(db, platform)


@router.patch("/{platform_id}", response_model=PlatformDetail, summary="Update name / cluster policy / configuration")
def update_platform(platform_id: uuid.UUID, payload: PlatformConfigUpdate, db: Session = Depends(get_db),
                    _: Principal = Depends(require(Perm.manage_platforms))) -> PlatformDetail:
    platform = platform_service.update_configuration(
        db, _require(db, platform_id), name=payload.name,
        cluster_policy=payload.cluster_policy.model_dump() if payload.cluster_policy else None,
        configuration=payload.configuration,
    )
    return detail(db, platform)


@router.get("/{platform_id}/overview", response_model=ConsoleOverviewResponse, summary="Command-centre overview")
def overview(platform_id: uuid.UUID, db: Session = Depends(get_db),
             _: Principal = Depends(require(Perm.view_console))) -> ConsoleOverviewResponse:
    return ConsoleOverviewResponse(**situation_service.console_overview(db, _require(db, platform_id)))


@router.get("/{platform_id}/map", response_model=MapFeatureCollection, summary="Internal map (precise coordinates)")
def internal_map(
    platform_id: uuid.UUID,
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    include_reports: bool = True,
    db: Session = Depends(get_db),
    _: Principal = Depends(require(Perm.view_console)),
) -> MapFeatureCollection:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    return MapFeatureCollection(**situation_service.map_collection(
        db, _require(db, platform_id), public=False, since=since, include_reports=include_reports
    ))


@router.get("/{platform_id}/reports", response_model=ReportListResponse, summary="Internal report list")
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
    principal: Principal = Depends(require(Perm.view_console)),
) -> ReportListResponse:
    _require(db, platform_id)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours) if since_hours else None
    rows, total = report_service.list_reports(
        db, platform_id, category=category, town=town, status=status_filter, severity=severity, since=since,
        limit=limit, offset=offset,
    )
    # the list never carries personal data; open a case or report to see it (logged)
    return ReportListResponse(items=[ReportInternal(**presenters.report_internal(r, include_pii=False)) for r in rows],
                              total=total, limit=limit, offset=offset)


@router.get("/{platform_id}/clusters", summary="Report clusters (open ones are candidates for 人工成案)")
def list_clusters(platform_id: uuid.UUID, status_filter: str | None = Query(default=None, alias="status"),
                  db: Session = Depends(get_db), _: Principal = Depends(require(Perm.view_console))) -> dict:
    _require(db, platform_id)
    rows = cluster_service.list_clusters(db, platform_id, status=status_filter)
    return {"items": [situation_service.cluster_feature(c, public=False)["properties"] | {
        "lat": c.centroid_lat, "lon": c.centroid_lon} for c in rows], "total": len(rows)}


@router.post("/{platform_id}/clusters/{cluster_id}/promote", response_model=CaseItem,
             summary="人工成案：未達門檻的通報直接送入審核")
def promote_cluster(platform_id: uuid.UUID, cluster_id: uuid.UUID, db: Session = Depends(get_db),
                    principal: Principal = Depends(require(Perm.review_cases))) -> CaseItem:
    platform = _require(db, platform_id)
    cluster = next((c for c in cluster_service.list_clusters(db, platform_id, limit=10000) if c.id == cluster_id), None)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    had_case = cluster.case_id is not None
    case = case_service.promote_cluster(db, platform, cluster, actor_name=principal.actor_name)
    db.commit()
    db.refresh(case)
    if not had_case:
        case_service.after_commit(db, platform, case, previous_status=None)
    return CaseItem(**presenters.case_item(case))


@router.get("/{platform_id}/layers", response_model=LayerStatusResponse, summary="Layer availability")
def layer_statuses(platform_id: uuid.UUID, db: Session = Depends(get_db),
                   _: Principal = Depends(require(Perm.view_console))) -> LayerStatusResponse:
    return LayerStatusResponse(items=official_data_service.layer_statuses(_require(db, platform_id)))


@router.get("/{platform_id}/layers/{layer}", response_model=LayerResponse, summary="Official data layer")
def get_layer(platform_id: uuid.UUID, layer: str, refresh: bool = False, db: Session = Depends(get_db),
              _: Principal = Depends(require(Perm.view_console))) -> LayerResponse:
    return LayerResponse(**official_data_service.get_layer(_require(db, platform_id), layer, force=refresh))


@router.get("/{platform_id}/audit", summary="Case / report event feed for this platform")
def audit(platform_id: uuid.UUID, limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0),
          db: Session = Depends(get_db), _: Principal = Depends(require(Perm.view_console))) -> dict:
    _require(db, platform_id)
    rows = outbox_service.list_platform_events(db, platform_id, limit=limit, offset=offset, exclude_prefixes=_FEED_EXCLUDE)
    return {"items": [{"id": str(e.id), "event_type": e.event_type, "aggregate_id": str(e.aggregate_id) if e.aggregate_id else None,
                       "payload": e.payload, "created_at": e.created_at.isoformat()} for e in rows]}


# ── LINE 群組通知 ─────────────────────────────────────────────────────────
class LineBindRequest(BaseModel):
    group_id: str = Field(..., min_length=10, max_length=64)


@router.get("/{platform_id}/line", summary="LINE 群組通知狀態（含綁定代碼）")
def line_status(platform_id: uuid.UUID, db: Session = Depends(get_db),
                principal: Principal = Depends(require(Perm.view_console))) -> dict:
    platform = _require(db, platform_id)
    info = line_service.status(db, platform)
    if not principal.can(Perm.manage_line):
        info["bind_code"] = None  # only administrators bind groups
    return info


@router.post("/{platform_id}/line/code", summary="重新產生綁定代碼")
def line_regenerate_code(platform_id: uuid.UUID, db: Session = Depends(get_db),
                         _: Principal = Depends(require(Perm.manage_line))) -> dict:
    platform = _require(db, platform_id)
    line_service.bind_code(db, platform, regenerate=True)
    return line_service.status(db, platform)


@router.put("/{platform_id}/line", summary="以群組 ID 手動綁定")
def line_bind(platform_id: uuid.UUID, payload: LineBindRequest, db: Session = Depends(get_db),
              principal: Principal = Depends(require(Perm.manage_line))) -> dict:
    platform = _require(db, platform_id)
    try:
        line_service.bind_group(db, platform, payload.group_id, actor=principal.actor_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return line_service.status(db, platform)


@router.delete("/{platform_id}/line", summary="解除 LINE 群組綁定")
def line_unbind(platform_id: uuid.UUID, db: Session = Depends(get_db),
                principal: Principal = Depends(require(Perm.manage_line))) -> dict:
    platform = _require(db, platform_id)
    line_service.unbind(db, platform, actor=principal.actor_name)
    return line_service.status(db, platform)


@router.post("/{platform_id}/line/test", summary="發送測試訊息到綁定的群組")
def line_test(platform_id: uuid.UUID, db: Session = Depends(get_db),
              principal: Principal = Depends(require(Perm.manage_line))) -> dict:
    platform = _require(db, platform_id)
    result = notification_service.staff_test(platform, principal.actor_name)
    return {"result": result}


@router.get("/{platform_id}/notifications", summary="通知紀錄（LINE／Email）")
def notifications(platform_id: uuid.UUID, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db),
                  _: Principal = Depends(require(Perm.view_console))) -> dict:
    _require(db, platform_id)
    rows = notification_service.recent_logs(db, platform_id, limit=limit)
    return {"items": [{"id": str(n.id), "channel": n.channel, "kind": n.kind, "recipient": n.recipient,
                       "status": n.status, "detail": n.detail, "case_id": str(n.case_id) if n.case_id else None,
                       "created_at": n.created_at.isoformat()} for n in rows]}
