"""Demo scenario seeder (DEMO_MODE only; protected by the API key gate)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.schemas.situation import GlobalOverviewResponse
from app.db.models import Platform
from app.services import demo_seed_service, platform_service, situation_service

router = APIRouter(prefix="/v1", tags=["demo"])


@router.post("/demo/nantou", summary="Seed the 南投豪雨 demo scenario through the real pipeline")
def seed_nantou(force: bool = False, db: Session = Depends(get_db)) -> dict:
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")
    return demo_seed_service.seed_nantou(db, force=force)


@router.get("/demo/nantou", summary="Locate the demo platform")
def get_demo(db: Session = Depends(get_db)) -> dict:
    p = demo_seed_service.find_demo_platform(db)
    if p is None:
        return {"exists": False}
    return {"exists": True, "platform_id": str(p.id), "slug": p.slug, "status": p.status}


@router.get("/overview", response_model=GlobalOverviewResponse, summary="Cross-platform overview", tags=["overview"])
def overview(db: Session = Depends(get_db)) -> GlobalOverviewResponse:
    return GlobalOverviewResponse(**situation_service.global_overview(db))


@router.post("/platforms/{platform_id}/demo", summary="Load the demo story into an existing platform (console 「帶入示範資料」)")
def seed_platform_demo(platform_id: uuid.UUID, replace: bool = False, db: Session = Depends(get_db)) -> dict:
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")
    platform = db.get(Platform, platform_id)
    if platform is None:
        raise HTTPException(status_code=404, detail="platform not found")
    return demo_seed_service.seed_into_platform(db, platform, replace=replace)


@router.post("/platforms/prune", summary="Retire generated platforms (keeps the built-in demo)")
def prune_platforms(keep: int = 0, db: Session = Depends(get_db)) -> dict:
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")
    removed = platform_service.prune_generated(db, keep=max(0, keep))
    return {"removed": removed, "count": len(removed)}
