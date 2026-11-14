from __future__ import annotations
from typing import Optional

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import ActivityEvent

router = APIRouter(prefix="/api/activity", tags=["analytics"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_activity(event_type: str, entity_id: Optional[UUID] = None, payload: Optional[dict] = None,
                          session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    event = ActivityEvent(user_id=user_id, type=event_type, entity_id=entity_id, payload=payload or {})
    session.add(event)
    await session.commit()
    return {"id": str(event.id), "recorded": True}

