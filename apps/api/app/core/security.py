"""Request authentication and permission checks for government endpoints.

Order of precedence for a request:
  1. ``Authorization: Bearer <token>`` of an active staff account;
  2. no credentials: allowed only in a development environment with
     AUTH_REQUIRED false (local development / tests) — a 開發模式 principal.
     Never available once ENVIRONMENT leaves development.
Otherwise 401. Permission failures are 403.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User
from app.domain.permissions import ALL_PERMS, ROLE_LABELS, Perm, perms_for


@dataclass
class Principal:
    kind: str  # user | service | dev
    name: str
    role: str | None
    perms: frozenset[Perm] = field(default_factory=frozenset)
    user: User | None = None

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def actor_name(self) -> str:
        if self.user is not None:
            return self.user.display_name
        return self.name

    def can(self, perm: Perm) -> bool:
        return perm in self.perms

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": str(self.user.id) if self.user else None,
            "username": self.user.username if self.user else None,
            "display_name": self.actor_name,
            "role": self.role,
            "role_label": ROLE_LABELS.get(self.role or "", "開發模式" if self.kind == "dev" else "系統服務"),
            "permissions": sorted(p.value for p in self.perms),
            "must_change_password": bool(self.user and self.user.must_change_password
                                         and settings.AUTH_FORCE_PASSWORD_CHANGE),
        }


def client_ip(request: Request) -> str | None:
    """The address rate limiting and the audit log key on.

    Only the hop added by our own reverse proxy can be trusted, so take the
    LAST entry of X-Forwarded-For (anything a client prepends itself sits to
    the left of it) — and only when the deployment says it runs behind a proxy.
    """
    if settings.TRUST_FORWARDED_FOR:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            hops = [h.strip() for h in fwd.split(",") if h.strip()]
            if hops:
                return hops[-1][:64]
    return request.client.host if request.client else None


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    from app.services import auth_service  # local: avoid import cycle at startup

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        user = auth_service.user_from_token(db, auth[7:].strip())
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登入已失效，請重新登入")
        return Principal(kind="user", name=user.username, role=user.role, perms=perms_for(user.role), user=user)
    if settings.is_development and not settings.AUTH_REQUIRED:
        return Principal(kind="dev", name="開發模式", role=None, perms=ALL_PERMS)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入")


def require(*perms: Perm):
    """Dependency factory: the caller must hold every listed permission."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        missing = [p for p in perms if not principal.can(p)]
        if missing:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="您的角色沒有此操作權限")
        return principal

    return _dep
