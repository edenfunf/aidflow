"""Break-glass: clear a staff account's failed-login lock.

A disaster is the worst moment to be locked out, and repeated failed logins
(including somebody guessing at an officer's username) lock an account for
AUTH_LOCK_MINUTES. Run this on the API host to release it:

    python scripts/unlock_user.py officer1          # one account
    python scripts/unlock_user.py --list            # who is locked right now

Needs DATABASE_URL in the environment (the same value the API uses).
The action is written to the audit trail as "user.unlocked".
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import User  # noqa: E402
from app.services import outbox_service  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="解除政府後台帳號的登入鎖定")
    ap.add_argument("username", nargs="?", help="要解鎖的帳號")
    ap.add_argument("--list", action="store_true", help="列出目前被鎖定的帳號")
    args = ap.parse_args()
    if not args.username and not args.list:
        ap.error("請指定帳號，或用 --list 查看目前鎖定中的帳號")

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        if args.list:
            locked = db.scalars(select(User).where(User.locked_until.is_not(None))).all()
            active = [u for u in locked if u.locked_until and u.locked_until > now]
            if not active:
                print("目前沒有被鎖定的帳號。")
                return 0
            for u in active:
                print(f"{u.username}\t鎖定至 {u.locked_until.isoformat()}\t失敗次數 {u.failed_attempts or 0}")
            return 0

        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            print(f"找不到帳號：{args.username}", file=sys.stderr)
            return 1
        was_locked = bool(user.locked_until and user.locked_until > now)
        user.locked_until = None
        user.failed_attempts = 0
        outbox_service.enqueue_event(
            db, event_type="user.unlocked", aggregate_id=user.id,
            payload={"username": user.username, "was_locked": was_locked, "by": "cli"},
        )
        db.commit()
        print(f"已解除 {user.username} 的登入鎖定" + ("" if was_locked else "（原本就沒有鎖定，失敗次數已歸零）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
