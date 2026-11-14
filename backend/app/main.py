from __future__ import annotations
from typing import Optional

from datetime import datetime, timezone
from fastapi import FastAPI
from .schemas import ChatRequest
from .services.quick_add import parse_quick_add
from .auth import current_user_id
from .db import get_session
from .services.chat_orchestrator import handle_chat
from .api.actions import router as actions_router
from .api.plan import router as plan_router
from .api.capacity import router as capacity_router
from .api.reminders import router as reminders_router
from .api.reminder_actions import router as reminder_actions_router
from .api.insights import router as insights_router
from .api.activity import router as activity_router
from .api.events import router as events_router
from .api.preferences import router as preferences_router
from .api.plan_blocks import router as plan_blocks_router
from .api.today import router as today_router
from .api.conflicts import router as conflicts_router
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select, text
import hashlib
import json
from .models import IdempotencyRecord
from .rate_limit import RateLimitMiddleware
from .api.tasks import router as tasks_router
from .api.task_batches import router as task_batches_router

app = FastAPI(title="LifeOS API", version="0.1.0")
app.add_middleware(RateLimitMiddleware)
app.include_router(tasks_router)
app.include_router(task_batches_router)
app.include_router(actions_router)
app.include_router(plan_router)
app.include_router(capacity_router)
app.include_router(reminders_router)
app.include_router(reminder_actions_router)
app.include_router(insights_router)
app.include_router(activity_router)
app.include_router(events_router)
app.include_router(preferences_router)
app.include_router(plan_blocks_router)
app.include_router(today_router)
app.include_router(conflicts_router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/api/chat")
async def chat(request: ChatRequest, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
               session: AsyncSession = Depends(get_session), user_id = Depends(current_user_id)) -> dict:
    if idempotency_key:
        await session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:owner), hashtext(:key))'),
                              {'owner': str(user_id), 'key': idempotency_key})
        request_hash = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()
        existing = (await session.execute(select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key, IdempotencyRecord.user_id == user_id))).scalar_one_or_none()
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(status_code=409, detail='Idempotency key reused with a different request')
            return existing.response
    result = await handle_chat(session, user_id=user_id, text=request.text, client_tz=request.client_tz)
    if idempotency_key:
        session.add(IdempotencyRecord(key=idempotency_key, user_id=user_id, response=result, request_hash=request_hash))
    await session.commit()
    return result

