"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.connectors import emic, line, mailer
from app.core.config import settings
from app.core.security import Principal, get_principal
from app.db.database import get_db
from app.domain.permissions import Perm

router = APIRouter(prefix="/v1", tags=["health"])


def _principal_or_none(request: Request, db=Depends(get_db)) -> Principal | None:
    """Health must answer anonymous monitors too, so a failed login is not an error."""
    from fastapi import HTTPException

    try:
        return get_principal(request, db)
    except HTTPException:
        return None


@router.get("/health", summary="Service health check")
def health(principal: Principal | None = Depends(_principal_or_none)) -> dict:
    body = {
        "status": "ok",
        "service": "aidflow-api",
        "auth_required": settings.AUTH_REQUIRED or bool(settings.ADMIN_API_KEY),
    }
    # version, demo mode and which channels are wired up are operational detail
    if principal is not None and principal.can(Perm.view_console):
        body.update(
            version=settings.APP_VERSION,
            demo_mode=settings.DEMO_MODE,
            channels={"line": line.is_configured(), "email": mailer.is_configured(), "emic": emic.mode()},
        )
    return body
