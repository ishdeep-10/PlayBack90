"""Lightweight in-memory rate limiting for the app's most compute-expensive endpoints
(PDF/PNG rendering, imports). Keyed by authenticated user id where available, falling
back to client IP. In-memory is fine for a single-instance deployment — if this ever
runs as multiple replicas, move the counters to Redis instead."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_hits: dict[str, list[float]] = defaultdict(list)
_MAX_TRACKED_KEYS = 5_000


def _identity(request: Request) -> str:
    auth_user = getattr(request.state, "auth_user", None)
    if auth_user is not None:
        return f"user:{auth_user.user_id}"
    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


def enforce_rate_limit(request: Request, *, bucket: str, limit: int, window_seconds: int) -> None:
    key = f"{bucket}:{_identity(request)}"
    now = time.monotonic()
    cutoff = now - window_seconds

    hits = _hits[key]
    while hits and hits[0] < cutoff:
        hits.pop(0)

    if len(hits) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again shortly.",
        )

    hits.append(now)

    if len(_hits) > _MAX_TRACKED_KEYS:
        stale = [k for k, v in _hits.items() if not v or v[-1] < cutoff]
        for k in stale:
            _hits.pop(k, None)


_window_counts: dict[str, tuple[float, int]] = {}


def enforce_fixed_window(request: Request, *, bucket: str, limit: int, window_seconds: int) -> None:
    """Cheap counter for long windows (an hour of sliding timestamps per user would cost memory)."""
    key = f"{bucket}:{_identity(request)}"
    now = time.monotonic()
    started, count = _window_counts.get(key, (now, 0))
    if now - started >= window_seconds:
        started, count = now, 0
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request limit reached. Please try again later.",
        )
    _window_counts[key] = (started, count + 1)
    if len(_window_counts) > _MAX_TRACKED_KEYS:
        for k in [k for k, (t, _) in _window_counts.items() if now - t >= window_seconds]:
            _window_counts.pop(k, None)
