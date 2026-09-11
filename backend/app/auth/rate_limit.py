"""Small in-memory sliding-window rate limiter (per client IP + bucket).

Sufficient for a single API instance; swap for Redis-backed limiting when the
API is scaled horizontally."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .security import client_ip


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests - please wait a minute and try again")
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def limiter_dependency(limiter: RateLimiter, bucket: str):
    def dep(request: Request) -> None:
        limiter.check(f"{bucket}:{client_ip(request)}")

    return dep
