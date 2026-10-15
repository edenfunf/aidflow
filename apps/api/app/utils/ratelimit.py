"""Per-IP sliding-window rate limiting for public write endpoints (濫用防護).

In-process and memory-only: enough for a single API instance. Behind several
instances put the limit on the reverse proxy as well.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            # keep memory bounded: forget idle keys occasionally
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    self._hits.pop(k, None)
            return True


_limiters: dict[str, SlidingWindowLimiter] = {}


def _limiter(name: str, limit: int) -> SlidingWindowLimiter:
    lim = _limiters.get(name)
    if lim is None or lim.limit != limit:
        lim = SlidingWindowLimiter(limit)
        _limiters[name] = lim
    return lim


def enforce(request: Request, name: str, limit: int) -> None:
    """Raise 429 when this client exceeded ``limit`` calls/minute for ``name``."""
    if not settings.RATE_LIMIT_ENABLED or limit <= 0:
        return
    from app.core.security import client_ip

    ip = client_ip(request) or "unknown"
    if not _limiter(name, limit).allow(ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="操作太頻繁，請稍候一分鐘再試")
