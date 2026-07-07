from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings


WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class RateLimitRule:
    path_prefix: str
    max_requests: int
    label: str


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings
        self._lock = Lock()
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._rules = [
            RateLimitRule("/api/run/stream", settings.rate_limit_run_stream_per_minute, "run_stream"),
            RateLimitRule("/api/run", settings.rate_limit_run_per_minute, "run"),
            RateLimitRule("/api/sessions/board/", settings.rate_limit_session_turn_per_minute, "board_turn"),
            RateLimitRule("/api/sessions/war-room/", settings.rate_limit_session_turn_per_minute, "war_turn"),
            RateLimitRule("/api/sessions/board", settings.rate_limit_session_start_per_minute, "board_start"),
            RateLimitRule("/api/sessions/war-room", settings.rate_limit_session_start_per_minute, "war_start"),
            RateLimitRule("/api/artifacts/pdf", settings.rate_limit_artifact_pdf_per_minute, "artifact_pdf"),
        ]

    async def dispatch(self, request: Request, call_next):
        if not self.settings.rate_limit_enabled:
            return await call_next(request)
        if request.method != "POST" and not request.url.path.startswith("/api/artifacts/pdf"):
            return await call_next(request)
        rule = self._match_rule(request.url.path)
        if rule is None:
            return await call_next(request)

        client_id = self._client_id(request)
        now = time.monotonic()
        retry_after = 0
        with self._lock:
            bucket = self._buckets.setdefault((client_id, rule.label), deque())
            while bucket and now - bucket[0] >= WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= rule.max_requests:
                retry_after = max(1, int(WINDOW_SECONDS - (now - bucket[0])))
            else:
                bucket.append(now)

        if retry_after:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded for {rule.label}. Retry in about {retry_after} seconds."
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    def _match_rule(self, path: str) -> RateLimitRule | None:
        for rule in self._rules:
            if path.startswith(rule.path_prefix):
                return rule
        return None

    def _client_id(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size_bytes: int = 5 * 1024 * 1024):  # 5MB default limit
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_size_bytes:
                        from fastapi.responses import JSONResponse
                        return JSONResponse(
                            status_code=413,
                            content={"detail": f"Request body too large. Maximum size is {self.max_size_bytes} bytes."}
                        )
                except ValueError:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=400, content={"detail": "Invalid content-length header."})
        return await call_next(request)

