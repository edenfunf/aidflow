"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.services import ai_agent

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", summary="Service health check")
def health() -> dict:
    return {
        "status": "ok",
        "service": "aidflow-api",
        "version": settings.APP_VERSION,
        "ai_enabled": ai_agent.is_enabled(),
        "demo_mode": settings.DEMO_MODE,
        "api_key_required": bool(settings.ADMIN_API_KEY),
    }
