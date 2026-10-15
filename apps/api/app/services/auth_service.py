"""Staff accounts and login (G-01 登入與帳號管理, S-08 身分驗證與授權).

- Passwords: Argon2id (argon2-cffi), never stored or logged in clear.
- Tokens: HS256 JWT carrying user id, role and the account's token_version;
  bumping token_version (password change, deactivation, role change) revokes
  every token issued before it.
- Lockout: AUTH_MAX_FAILED_ATTEMPTS consecutive failures lock the account for
  AUTH_LOCK_MINUTES. The response never says whether the username exists.
- Every login, failure, lockout and account change is written to the outbox
  as an ``auth.*`` / ``user.*`` audit event.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.domain.permissions import ROLE_LABELS, Role
from app.services import outbox_service

_hasher = PasswordHasher()
_ALGO = "HS256"
# verified against when the username does not exist, so timing does not leak it
_DUMMY_HASH = _hasher.hash("aidflow-timing-equaliser")


class AuthError(Exception):
    """Login failed. ``locked_until`` is set when the account is locked."""

    def __init__(self, message: str, *, locked_until: datetime | None = None) -> None:
        super().__init__(message)
        self.locked_until = locked_until


class AccountError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password(password: str) -> None:
    """Minimum length plus at least two character classes."""
    if len(password) < settings.AUTH_MIN_PASSWORD_LENGTH:
        raise AccountError(f"密碼至少需 {settings.AUTH_MIN_PASSWORD_LENGTH} 個字元")
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if classes < 2:
        raise AccountError("密碼需包含英文大小寫、數字或符號中至少兩種")


def _audit(db: Session, event_type: str, user: User | None, **payload) -> None:
    outbox_service.enqueue_event(
        db, event_type=event_type, aggregate_id=user.id if user else None,
        payload={"user_id": str(user.id) if user else None, "username": user.username if user else None, **payload},
    )


# ── tokens ────────────────────────────────────────────────────────────────
def issue_token(user: User) -> tuple[str, datetime]:
    exp = _now() + timedelta(hours=settings.AUTH_TOKEN_HOURS)
    token = jwt.encode(
        {"sub": str(user.id), "role": user.role, "ver": user.token_version, "exp": exp, "iat": _now()},
        settings.AUTH_SECRET, algorithm=_ALGO,
    )
    return token, exp


def user_from_token(db: Session, token: str) -> User | None:
    try:
        claims = jwt.decode(token, settings.AUTH_SECRET, algorithms=[_ALGO])
        user_id = uuid.UUID(str(claims.get("sub")))
    except (jwt.PyJWTError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.active or user.token_version != claims.get("ver"):
        return None
    return user


# ── login ─────────────────────────────────────────────────────────────────
def login(db: Session, username: str, password: str, *, ip: str | None) -> tuple[User, str, datetime]:
    name = (username or "").strip().lower()
    user = db.scalar(select(User).where(func.lower(User.username) == name))
    now = _now()
    if user is None:
        verify_password(_DUMMY_HASH, password)
        _audit(db, "auth.login_failed", None, attempted_username=name[:64], ip=ip, reason="unknown_user")
        db.commit()
        raise AuthError("帳號或密碼錯誤")
    if user.locked_until and user.locked_until > now:
        _audit(db, "auth.login_blocked", user, ip=ip)
        db.commit()
        raise AuthError("帳號暫時鎖定，請稍後再試", locked_until=user.locked_until)
    if not user.active or not verify_password(user.password_hash, password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        locked = None
        if user.failed_attempts >= settings.AUTH_MAX_FAILED_ATTEMPTS:
            locked = now + timedelta(minutes=settings.AUTH_LOCK_MINUTES)
            user.locked_until = locked
            user.failed_attempts = 0
            _audit(db, "auth.account_locked", user, ip=ip, minutes=settings.AUTH_LOCK_MINUTES)
        _audit(db, "auth.login_failed", user, ip=ip, reason="inactive" if not user.active else "bad_password")
        db.commit()
        if locked:
            raise AuthError("登入失敗次數過多，帳號暫時鎖定", locked_until=locked)
        raise AuthError("帳號或密碼錯誤")
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    _audit(db, "auth.login", user, ip=ip, role=user.role)
    db.commit()
    db.refresh(user)
    token, exp = issue_token(user)
    return user, token, exp


def logout(db: Session, user: User, *, ip: str | None) -> None:
    # the signed-out token stops working immediately (see the "ver" claim in issue_token)
    user.token_version = (user.token_version or 0) + 1
    _audit(db, "auth.logout", user, ip=ip)
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> tuple[str, datetime]:
    if not verify_password(user.password_hash, current):
        raise AccountError("目前密碼不正確")
    validate_password(new)
    if verify_password(user.password_hash, new):
        raise AccountError("新密碼不可與目前密碼相同")
    user.password_hash = hash_password(new)
    user.token_version += 1
    user.must_change_password = False
    _audit(db, "user.password_changed", user, by="self")
    db.commit()
    db.refresh(user)
    return issue_token(user)


# ── account management (admin) ────────────────────────────────────────────
def _check_role(role: str) -> None:
    if role not in {r.value for r in Role}:
        raise AccountError("未知的角色：" + role)


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.asc())).all())


def create_user(db: Session, *, username: str, display_name: str, role: str, password: str,
                actor: str | None, must_change_password: bool | None = None) -> User:
    if must_change_password is None:
        must_change_password = settings.AUTH_FORCE_PASSWORD_CHANGE
    name = username.strip().lower()
    if not name or not all(c.isalnum() or c in "._-" for c in name):
        raise AccountError("帳號只能使用英數字與 . _ -")
    _check_role(role)
    validate_password(password)
    if db.scalar(select(User.id).where(func.lower(User.username) == name)):
        raise AccountError("此帳號已存在")
    user = User(username=name, display_name=display_name.strip() or name, role=role,
                password_hash=hash_password(password), must_change_password=must_change_password)
    db.add(user)
    db.flush()
    _audit(db, "user.created", user, role=role, role_label=ROLE_LABELS.get(role), by=actor)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, *, actor_user: User | None, actor: str | None,
                display_name: str | None = None, role: str | None = None, active: bool | None = None,
                password: str | None = None) -> User:
    changes: dict = {}
    if display_name is not None and display_name.strip() and display_name.strip() != user.display_name:
        user.display_name = display_name.strip()
        changes["display_name"] = user.display_name
    if role is not None and role != user.role:
        _check_role(role)
        if actor_user is not None and actor_user.id == user.id:
            raise AccountError("不可變更自己的角色")
        _ensure_admin_remains(db, user, new_role=role)
        user.role = role
        user.token_version += 1
        changes["role"] = role
    if active is not None and active != user.active:
        if actor_user is not None and actor_user.id == user.id and not active:
            raise AccountError("不可停用自己的帳號")
        if not active:
            _ensure_admin_remains(db, user, new_active=False)
        user.active = active
        user.token_version += 1
        changes["active"] = active
    if password:
        validate_password(password)
        user.password_hash = hash_password(password)
        user.token_version += 1
        user.must_change_password = settings.AUTH_FORCE_PASSWORD_CHANGE
        user.failed_attempts = 0
        user.locked_until = None
        changes["password_reset"] = True
    if changes:
        _audit(db, "user.updated", user, changes=changes, by=actor)
    db.commit()
    db.refresh(user)
    return user


def _ensure_admin_remains(db: Session, user: User, *, new_role: str | None = None, new_active: bool | None = None) -> None:
    if user.role != Role.admin.value or not user.active:
        return
    still_admin = (new_role or user.role) == Role.admin.value and (new_active if new_active is not None else user.active)
    if still_admin:
        return
    others = db.scalar(select(func.count()).select_from(User).where(
        User.role == Role.admin.value, User.active.is_(True), User.id != user.id)) or 0
    if not others:
        raise AccountError("至少需保留一位啟用中的系統管理者")


def bootstrap_admin(db: Session) -> User | None:
    """First start: create the initial administrator from the environment
    when the users table is empty."""
    if not settings.INITIAL_ADMIN_PASSWORD:
        return None
    if db.scalar(select(func.count()).select_from(User)):
        return None
    user = User(username=settings.INITIAL_ADMIN_USERNAME.strip().lower() or "admin", display_name="系統管理者",
                role=Role.admin.value, password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
                must_change_password=settings.AUTH_FORCE_PASSWORD_CHANGE)
    db.add(user)
    db.flush()
    _audit(db, "user.created", user, role=user.role, by="bootstrap")
    db.commit()
    db.refresh(user)
    return user
