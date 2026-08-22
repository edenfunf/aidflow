"""Agent planner endpoints.

``/plan`` understands a brief and proposes a platform (no side effects other
than an audit event); ``/execute`` composes the human-approved draft. The split
is the approval gate — a plan can never modify production on its own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.routers.platforms import detail as platform_detail
from app.schemas.agent import AgentExecuteRequest, AgentExecuteResponse, AgentPlanRequest, AgentPlanResponse
from app.services import agent_orchestrator
from app.services.platform_service import InvalidSelectionError

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.post("/plan", response_model=AgentPlanResponse, summary="Understand a disaster brief and propose a platform")
def plan(payload: AgentPlanRequest, db: Session = Depends(get_db)) -> AgentPlanResponse:
    result = agent_orchestrator.plan(db, payload.message)
    result.pop("_role_labels", None)
    return AgentPlanResponse(**result)


@router.post("/execute", response_model=AgentExecuteResponse, status_code=status.HTTP_201_CREATED,
             summary="Compose the approved plan into a platform")
def execute(payload: AgentExecuteRequest, db: Session = Depends(get_db)) -> AgentExecuteResponse:
    try:
        result = agent_orchestrator.execute(db, payload)
        platform = result["platform"]
    except InvalidSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    base = settings.WEB_PUBLIC_BASE_URL.rstrip("/")
    return AgentExecuteResponse(
        platform=platform_detail(db, platform),
        public_url=f"{base}/p/{platform.slug}",
        console_url=f"{base}/console/platforms/{platform.id}",
        retired=result.get("retired", []),
        enabled_modules=len(platform.modules or []),
        enabled_layers=len(platform.layers or []),
    )
