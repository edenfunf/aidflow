"""LINE group binding (G-09 LINE 群組綁定設定).

How a county connects its notification group to a platform:

  1. 系統管理者 opens the platform's LINE settings and reads the 6-character
     binding code.
  2. Someone invites the LINE bot into the county's notification group.
  3. In the group, send 「綁定 ABC123」. The webhook (signature-verified)
     binds that group to the platform and replies with a confirmation.

A group id can also be entered by hand. Only one group per platform; binding a
new one replaces the old.
"""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.connectors import line
from app.connectors.base import ConnectorError
from app.db.models import LineGroup, Platform
from app.services import outbox_service

_CODE_ALPHABET = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
_BIND_RE = re.compile(r"^\s*綁定\s*([A-Za-z0-9]{6})\s*$")
_GROUP_ID_RE = re.compile(r"^[CR][0-9a-f]{32}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_config(platform: Platform, **values) -> None:
    cfg = dict(platform.configuration or {})
    for k, v in values.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    platform.configuration = cfg
    flag_modified(platform, "configuration")


def bind_code(db: Session, platform: Platform, *, regenerate: bool = False) -> str:
    code = (platform.configuration or {}).get("line_bind_code")
    if code and not regenerate:
        return code
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
    _set_config(platform, line_bind_code=code)
    db.commit()
    return code


def status(db: Session, platform: Platform) -> dict:
    cfg = platform.configuration or {}
    group_id = cfg.get("line_group_id")
    return {
        "token_configured": line.is_configured(),
        "webhook_enabled": line.webhook_enabled(),
        "bound": bool(group_id),
        "group_id_masked": f"{group_id[:8]}…" if group_id else None,
        "bound_at": cfg.get("line_bound_at"),
        "bind_code": bind_code(db, platform),
        "webhook_path": "/v1/line/webhook",
    }


def bind_group(db: Session, platform: Platform, group_id: str, *, actor: str) -> None:
    group_id = group_id.strip()
    if not _GROUP_ID_RE.match(group_id):
        raise ValueError("LINE 群組 ID 格式不正確（應為 C 開頭、33 碼）")
    row = db.scalar(select(LineGroup).where(LineGroup.group_id == group_id))
    if row is None:
        row = LineGroup(group_id=group_id)
        db.add(row)
    # a group notifies one platform; a platform notifies one group
    for other in db.scalars(select(LineGroup).where(LineGroup.platform_id == platform.id,
                                                    LineGroup.group_id != group_id)).all():
        other.platform_id = None
        other.status = "joined"
    if row.platform_id and row.platform_id != platform.id:
        previous = db.get(Platform, row.platform_id)
        if previous is not None and (previous.configuration or {}).get("line_group_id") == group_id:
            _set_config(previous, line_group_id=None, line_bound_at=None)
    row.platform_id = platform.id
    row.status = "bound"
    row.bound_at = _now()
    _set_config(platform, line_group_id=group_id, line_bound_at=row.bound_at.isoformat())
    outbox_service.enqueue_event(db, event_type="line.group_bound", aggregate_id=platform.id,
                                 payload={"platform_id": str(platform.id), "group": group_id[:8], "by": actor})
    db.commit()


def unbind(db: Session, platform: Platform, *, actor: str) -> None:
    group_id = (platform.configuration or {}).get("line_group_id")
    if group_id:
        row = db.scalar(select(LineGroup).where(LineGroup.group_id == group_id))
        if row is not None:
            row.platform_id = None
            row.status = "joined"
    _set_config(platform, line_group_id=None, line_bound_at=None)
    outbox_service.enqueue_event(db, event_type="line.group_unbound", aggregate_id=platform.id,
                                 payload={"platform_id": str(platform.id), "by": actor})
    db.commit()


def _reply(token: str | None, text: str) -> None:
    if not token or not line.is_configured():
        return
    try:
        line.reply_text(token, text)
    except ConnectorError:
        pass


def handle_webhook(db: Session, body: dict) -> int:
    """Process verified webhook events. Returns how many were handled."""
    handled = 0
    for ev in body.get("events") or []:
        source = ev.get("source") or {}
        group_id = source.get("groupId") or source.get("roomId")
        if not group_id:
            continue
        etype = ev.get("type")
        if etype == "join":
            row = db.scalar(select(LineGroup).where(LineGroup.group_id == group_id))
            if row is None:
                db.add(LineGroup(group_id=group_id, status="joined"))
            elif row.status == "left":
                row.status = "joined"
            db.commit()
            _reply(ev.get("replyToken"),
                   "AidFlow 災情通報機器人已加入。\n請系統管理者在政府管理後台取得綁定代碼，並在此群組輸入「綁定 代碼」。")
            handled += 1
        elif etype == "leave":
            row = db.scalar(select(LineGroup).where(LineGroup.group_id == group_id))
            if row is not None:
                if row.platform_id:
                    p = db.get(Platform, row.platform_id)
                    if p is not None and (p.configuration or {}).get("line_group_id") == group_id:
                        _set_config(p, line_group_id=None, line_bound_at=None)
                row.platform_id = None
                row.status = "left"
                db.commit()
            handled += 1
        elif etype == "message" and (ev.get("message") or {}).get("type") == "text":
            m = _BIND_RE.match((ev["message"].get("text") or ""))
            if not m:
                continue
            code = m.group(1).upper()
            platform = next(
                (p for p in db.scalars(select(Platform)).all() if (p.configuration or {}).get("line_bind_code") == code),
                None,
            )
            if platform is None:
                _reply(ev.get("replyToken"), "綁定代碼不正確，請確認後台顯示的代碼。")
                continue
            try:
                bind_group(db, platform, group_id, actor="LINE 群組綁定")
            except ValueError:
                _reply(ev.get("replyToken"), "此聊天室無法綁定，請在 LINE 群組中操作。")
                continue
            _reply(ev.get("replyToken"), f"已綁定「{platform.name}」。之後有新災情通報時，會通知本群組。")
            handled += 1
    return handled
