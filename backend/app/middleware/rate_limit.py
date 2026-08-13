"""간단한 IP 기반 Rate Limit 미들웨어 (단기 공유·비용 방어).

읽기(GET/HEAD/OPTIONS)는 제한하지 않고, 비용·쓰기 요청만 제한합니다.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# LLM·업로드 등 비용/부하가 큰 경로만 제한
_LIMITED_PREFIXES = (
    "/api/inquiry/generate",
    "/api/inquiry/",  # regenerate, feedback 등
    "/api/plans/",
    "/api/budget/",
    "/api/documents/upload",
    "/api/documents/ingest",
    "/api/analytics/",
    "/api/forms/generate",
)


def _should_limit(method: str, path: str) -> bool:
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if path in ("/api/health", "/"):
        return False
    return path.startswith("/api/") and any(path.startswith(p) for p in _LIMITED_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP당 분당 N회 — 쓰기/생성 API에만 적용."""

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        if self.max_requests <= 0 or not _should_limit(request.method, request.url.path):
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()
        window = self._hits[ip]
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"요청이 너무 많습니다. IP당 분당 {self.max_requests}회로 제한됩니다. "
                        "잠시 후 다시 시도해 주세요."
                    )
                },
            )

        window.append(now)
        return await call_next(request)
