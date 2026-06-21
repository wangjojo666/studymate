from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings


@dataclass(frozen=True)
class RateLimitRule:
    bucket: str
    limit: int


_hits: dict[str, deque[float]] = defaultdict(deque)


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rule = _match_rule(request)
        if rule is None or not settings.rate_limit_enabled:
            return await call_next(request)

        now = time.monotonic()
        window = max(1, settings.rate_limit_window_seconds)
        key = _rate_limit_key(request, rule.bucket)
        entries = _hits[key]
        while entries and now - entries[0] > window:
            entries.popleft()
        if len(entries) >= rule.limit:
            retry_after = max(1, int(window - (now - entries[0]))) if entries else window
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试。"},
                headers={"Retry-After": str(retry_after)},
            )
        entries.append(now)
        return await call_next(request)


def clear_rate_limit_state() -> None:
    _hits.clear()


def _match_rule(request: Request) -> RateLimitRule | None:
    if request.method != "POST":
        return None
    path = request.url.path
    prefix = settings.api_prefix.rstrip("/")
    if path == f"{prefix}/auth/login":
        return RateLimitRule("login", settings.rate_limit_login_per_minute)
    if path.endswith("/ask") and f"{prefix}/courses/" in path:
        return RateLimitRule("ask", settings.rate_limit_ask_per_minute)
    if path.endswith("/documents") and f"{prefix}/courses/" in path:
        return RateLimitRule("upload", settings.rate_limit_upload_per_minute)
    return None


def _rate_limit_key(request: Request, bucket: str) -> str:
    auth = request.headers.get("authorization", "")
    identity = auth or (request.client.host if request.client else "unknown")
    digest = sha256(identity.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{bucket}:{digest}"
