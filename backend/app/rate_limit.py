from __future__ import annotations
from typing import Optional


import time
import math
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, *, identity: str, bucket: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        queue = self.events[(identity, bucket)]
        while queue and now - queue[0] >= window_seconds:
            queue.popleft()
        if len(queue) >= limit:
            retry_after = max(1, math.ceil(window_seconds - (now - queue[0])))
            return False, retry_after
        queue.append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limiter: Optional[SlidingWindowLimiter] = None) -> None:
        super().__init__(app)
        self.limiter = limiter or SlidingWindowLimiter()

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith('/api/'):
            return await call_next(request)
        from fastapi import HTTPException
        from .auth import current_user_id
        from .config import get_settings
        settings = get_settings()
        try:
            identity = str(await current_user_id(request.headers.get('authorization'), request.headers.get('x-demo-user-id')))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={'code': 'authentication_failed', 'message': exc.detail})
        limits = [('api', settings.api_rate_limit)]
        if request.url.path == "/api/chat":
            limits.append(('chat', settings.chat_rate_limit))
        elif request.url.path == "/api/voice/transcribe":
            limits.append(('transcription', settings.transcription_rate_limit))
        for bucket, limit in limits:
            allowed, retry_after = self.limiter.allow(identity=identity, bucket=bucket, limit=limit)
            if not allowed:
                return JSONResponse(status_code=429, content={"code": "rate_limited", "message": "Too many requests"}, headers={"Retry-After": str(retry_after)})
        return await call_next(request)

