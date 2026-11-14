from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..config import get_settings
from ..db import get_session
from ..models import PushSubscription
from ..services.push_service import allowed_endpoint

router = APIRouter(prefix="/api/push", tags=["reminders"])


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: SubscriptionKeys

    @field_validator('endpoint')
    @classmethod
    def push_service_only(cls, value: str) -> str:
        # The worker POSTs to this URL, so only known browser push services are allowed.
        if not allowed_endpoint(value, get_settings().push_allowed_host_list):
            raise ValueError('Endpoint must belong to a browser push service')
        return value


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
    values = {'user_id': user_id, 'endpoint': payload.endpoint, 'p256dh': payload.keys.p256dh,
              'auth': payload.keys.auth}
    dialect = session.get_bind().dialect.name
    if dialect == 'postgresql':
        # A browser endpoint belongs to one user: drop the previous owner's row
        # (shared browser, account switch) so their reminders stop arriving here.
        await session.execute(text('SELECT public.claim_push_endpoint(:endpoint)'), {'endpoint': payload.endpoint})
        from sqlalchemy.dialects.postgresql import insert
    else:
        await session.execute(delete(PushSubscription).where(PushSubscription.endpoint == payload.endpoint,
                                                             PushSubscription.user_id != user_id))
        from sqlalchemy.dialects.sqlite import insert
    # Upsert: concurrent first subscriptions from the same browser cannot collide.
    statement = insert(PushSubscription).values(**values)
    statement = statement.on_conflict_do_update(index_elements=['user_id', 'endpoint'],
        set_={'p256dh': statement.excluded.p256dh, 'auth': statement.excluded.auth})
    await session.execute(statement)
    row = (await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id,
        PushSubscription.endpoint == payload.endpoint))).scalar_one()
    await session.commit()
    return {"id": str(row.id), "endpoint": row.endpoint}


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(payload: Unsubscribe, session: AsyncSession = Depends(get_session),
                      user_id: UUID = Depends(current_user_id)) -> None:
    await session.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id,
        PushSubscription.endpoint == payload.endpoint))
    await session.commit()
