"""Response headers and a per-client limit for the public API."""

from __future__ import annotations

import os
from collections import deque
from threading import Lock
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# A person moving through the desk makes a handful of calls. This stops a tight loop.
LIMIT = 120
WINDOW_SECONDS = 60.0

_hits: dict[str, deque[float]] = {}
_lock = Lock()

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def reset() -> None:
    with _lock:
        _hits.clear()


def client_key(request: Request) -> str:
    """Use the address the platform appended, only when this process sits behind that proxy.

    Cloud Run and nginx append the connecting address at the end of X-Forwarded-For.
    A header sent straight to Uvicorn is ignored, so it cannot pick its own bucket.
    """
    if os.environ.get("TRUST_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip() if forwarded else ""
        if last:
            return last
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/") or path == "/api/health":
            return await call_next(request)
        now = monotonic()
        key = client_key(request)
        with _lock:
            bucket = _hits.setdefault(key, deque())
            while bucket and now - bucket[0] > WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= LIMIT:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": "60"},
                )
            bucket.append(now)
        return await call_next(request)
