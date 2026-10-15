"""Login and account management (G-01)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import Principal, client_ip, get_principal, require
from app.db.database import get_db
from app.db.models import EventOutbox, User
from app.domain.permissions import ROLE_LABELS, Perm, perms_for
from app.services import auth_service
from app.services.auth_service import AccountError, AuthError
from app.utils import ratelimit

router = APIRouter(prefix="/v1", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=1, max_length=200)


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=60)
    role: str
    password: str = Field(..., min_length=1, max_length=200)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200,
                                 description="重設密碼（AUTH_FORCE_PASSWORD_CHANGE 開啟時，使用者下次登入須變更）")


class UserItem(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    role_label: str
    active: bool
    locked: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime


def _user_item(u: User) -> UserItem:
    now = datetime.now(timezone.utc)
    return UserItem(id=u.id, username=u.username, display_name=u.display_name, role=u.role,
                    role_label=ROLE_LABELS.get(u.role, u.role), active=u.active,
                    locked=bool(u.locked_until and u.locked_until > now),
                    must_change_password=u.must_change_password and settings.AUTH_FORCE_PASSWORD_CHANGE,
                    last_login_at=u.last_login_at,
                    created_at=u.created_at)


@router.post("/auth/login", summary="登入（取得權杖）")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    ratelimit.enforce(request, "login", settings.RATE_LIMIT_LOGIN_PER_MINUTE)
    try:
        user, token, exp = auth_service.login(db, payload.username, payload.password, ip=client_ip(request))
    except AuthError as exc:
        detail: dict | str = str(exc)
        if exc.locked_until:
            detail = {"message": str(exc), "locked_until": exc.locked_until.isoformat()}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    principal = Principal(kind="user", name=user.username, role=user.role, perms=perms_for(user.role), user=user)
    return {"token": token, "expires_at": exp.isoformat(), "user": principal.to_dict()}


@router.get("/auth/me", summary="目前登入者與權限")
def me(principal: Principal = Depends(get_principal)) -> dict:
    return principal.to_dict()


@router.post("/auth/logout", summary="登出（寫入稽核紀錄）")
def logout(request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    if principal.user is not None:
        auth_service.logout(db, principal.user, ip=client_ip(request))
    return {"ok": True}


@router.post("/auth/password", summary="變更自己的密碼")
def change_password(payload: PasswordChangeRequest, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)) -> dict:
    if principal.user is None:
        raise HTTPException(status_code=400, detail="此身分沒有可變更的密碼")
    try:
        token, exp = auth_service.change_password(db, principal.user, payload.current_password, payload.new_password)
    except AccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"token": token, "expires_at": exp.isoformat()}


# ── users (系統管理者) ────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserItem], summary="帳號清單")
def list_users(db: Session = Depends(get_db), _: Principal = Depends(require(Perm.manage_users))) -> list[UserItem]:
    return [_user_item(u) for u in auth_service.list_users(db)]


@router.post("/users", response_model=UserItem, status_code=status.HTTP_201_CREATED, summary="新增帳號")
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db),
                principal: Principal = Depends(require(Perm.manage_users))) -> UserItem:
    try:
        user = auth_service.create_user(db, username=payload.username, display_name=payload.display_name,
                                        role=payload.role, password=payload.password, actor=principal.actor_name)
    except AccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _user_item(user)


@router.patch("/users/{user_id}", response_model=UserItem, summary="修改帳號（名稱、角色、啟停用、重設密碼）")
def update_user(user_id: uuid.UUID, payload: UserUpdateRequest, db: Session = Depends(get_db),
                principal: Principal = Depends(require(Perm.manage_users))) -> UserItem:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="帳號不存在")
    try:
        user = auth_service.update_user(db, user, actor_user=principal.user, actor=principal.actor_name,
                                        display_name=payload.display_name, role=payload.role,
                                        active=payload.active, password=payload.password or None)
    except AccountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _user_item(user)


@router.get("/roles", summary="角色清單")
def roles(_: Principal = Depends(require(Perm.view_console))) -> dict:
    return {"items": [{"key": k, "label": v} for k, v in ROLE_LABELS.items()]}


# ── security audit (業務主管／系統管理者) ────────────────────────────────
_SECURITY_PREFIXES = ("auth.", "user.", "pii.", "line.", "platform.")


@router.get("/admin/audit", summary="稽核紀錄（登入、帳號、個資查閱、平台設定）")
def security_audit(
    kind: str | None = Query(default=None, description="auth | user | pii | line | platform"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Principal = Depends(require(Perm.view_audit)),
) -> dict:
    # exact category, not a prefix match: kind="a" must not silently mean "auth."
    wanted = (kind or "").strip().rstrip(".")
    prefixes = tuple(p for p in _SECURITY_PREFIXES if not wanted or p == f"{wanted}.")
    q = select(EventOutbox)
    q = q.where(or_(*[EventOutbox.event_type.startswith(p) for p in prefixes])) if prefixes else q.where(false())
    rows = db.scalars(q.order_by(EventOutbox.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [{"id": str(e.id), "event_type": e.event_type, "payload": e.payload,
                       "created_at": e.created_at.isoformat()} for e in rows]}
