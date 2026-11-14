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
        self.expirations = {}
        self.events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, *, identity: str, bucket: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        if limit <= 0:
            return False, window_seconds
        now = time.monotonic()
        for key, expires in list(self.expirations.items()):
            if expires <= now:
                self.events.pop(key, None)
                self.expirations.pop(key, None)
        self.expirations[(identity, bucket)] = now + window_seconds
        queue = self.events[(identity, bucket)]
        while queue and now - queue[0] >= window_seconds:
            queue.popleft()
        if len(queue) >= limit:
            retry_after = max(1, math.ceil(window_seconds - (now - queue[0])))
            return False, retry_after
        queue.append(now)
        return True, 0


class PostgresWindowLimiter:
    async def allow(self, *, identity, bucket, limit, window_seconds=60):
        if limit <= 0:
            return False, window_seconds
        if window_seconds != 60:
            raise ValueError('Shared rate limits use a 60-second window')
        from sqlalchemy import text
        from .db import SessionFactory
        async with SessionFactory() as session, session.begin():
            session.info['user_id'] = identity
            await session.execute(text('SELECT pg_advisory_xact_lock(7302, hashtext(:key))'),
                                  {'key': identity + ':' + bucket})
            now = (await session.execute(text('SELECT clock_timestamp()'))).scalar_one()
            await session.execute(text('SELECT public.prune_rate_limit_events()'))
            count, first = (await session.execute(text(
                'SELECT count(*), min(occurred_at) FROM rate_limit_events WHERE user_id=:owner AND bucket=:bucket'),
                {'owner': identity, 'bucket': bucket})).one()
            if count >= limit:
                return False, max(1, math.ceil(window_seconds - (now - first).total_seconds()))
            await session.execute(text('INSERT INTO rate_limit_events(user_id,bucket,occurred_at) VALUES (:owner,:bucket,:now)'),
                                  {'owner': identity, 'bucket': bucket, 'now': now})
            return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limiter: Optional[SlidingWindowLimiter] = None) -> None:
        super().__init__(app)
        self.limiter = limiter or PostgresWindowLimiter()

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
        if request.method == "POST" and request.url.path == "/api/import/syllabus/extract":
            limits.append(('import', 10))  # each extraction is a large model call
        if request.method == "POST" and request.url.path in ("/api/voice/transcribe/quota", "/api/voice/speak/quota"):
            limits.append(('stt' if '/transcribe/' in request.url.path else 'tts', 5))
        for bucket, limit in limits:
            result = self.limiter.allow(identity=identity, bucket=bucket, limit=limit)
            import inspect
            allowed, retry_after = await result if inspect.isawaitable(result) else result
            if not allowed:
                return JSONResponse(status_code=429, content={"code": "rate_limited", "message": "Too many requests"}, headers={"Retry-After": str(retry_after)})
        return await call_next(request)

