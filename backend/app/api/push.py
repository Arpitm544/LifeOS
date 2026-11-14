from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..config import get_settings
from ..db import get_session
from ..models import PushSubscription

router = APIRouter(prefix="/api/push", tags=["reminders"])


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048, pattern=r'^https://')
    keys: SubscriptionKeys


class Unsubscribe(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)


@router.get("/public-key")
async def public_key(user_id=Depends(current_user_id)) -> dict:
    key = get_settings().vapid_public_key
    if not key:
        raise HTTPException(status_code=503, detail='Web Push is not configured on this server')
    return {"public_key": key}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(payload: SubscriptionIn, session: AsyncSession = Depends(get_session),
                    user_id: UUID = Depends(current_user_id)) -> dict:
    row = (await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id,
        PushSubscription.endpoint == payload.endpoint))).scalar_one_or_none()
    if row is None:
        row = PushSubscription(user_id=user_id, endpoint=payload.endpoint)
        session.add(row)
    row.p256dh, row.auth = payload.keys.p256dh, payload.keys.auth
    await session.commit()
    return {"id": str(row.id), "endpoint": row.endpoint}


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(payload: Unsubscribe, session: AsyncSession = Depends(get_session),
                      user_id: UUID = Depends(current_user_id)) -> None:
    await session.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id,
        PushSubscription.endpoint == payload.endpoint))
    await session.commit()
