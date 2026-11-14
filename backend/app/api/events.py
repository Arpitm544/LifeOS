from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import Event
from ..schemas_events import EventCreate, EventPatch
from ..services.domain_service import audit, snapshot



router = APIRouter(prefix="/api/events", tags=["events"])


@router.patch('/{event_id}')
async def edit_event(event_id: UUID, payload: EventPatch,
    session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    row = (await session.execute(select(Event).where(Event.id == event_id,
        Event.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Event not found')
    before = snapshot(row)
    merged = {key: getattr(row, key) for key in EventCreate.model_fields}
    merged.update(payload.model_dump(exclude_unset=True))
    from pydantic import ValidationError
    try:
        validated = EventCreate.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail='Invalid event edit') from exc
    for key, value in validated.model_dump().items():
        setattr(row, key, value)
    action = await audit(session, user_id, row, before, 'update')
    await session.commit()
    return {'event': snapshot(row), 'action_id': str(action.id)}


@router.get("")
async def list_events(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> list[dict]:
    events = (await session.execute(select(Event).where(Event.user_id == user_id, Event.cancelled == False).order_by(Event.start_at))).scalars().all()
    return [{"id": str(event.id), "title": event.title, "start_at": event.start_at, "end_at": event.end_at,
             "location": event.location, "rrule": event.rrule, "source": event.source} for event in events]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventCreate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    event = Event(user_id=user_id, **payload.model_dump())
    session.add(event)
    await session.flush()
    await audit(session, user_id, event, None, 'create')
    await session.commit()
    await session.refresh(event)
    return {"id": str(event.id), "title": event.title, "start_at": event.start_at, "end_at": event.end_at,
            "location": event.location, "rrule": event.rrule, "source": event.source}


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: UUID, confirmed: bool = False, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> None:
    if not confirmed:
        raise HTTPException(status_code=409, detail='Explicit confirmation required: confirmed=true')
    event = (await session.execute(select(Event).where(Event.id == event_id, Event.user_id == user_id))).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    before = snapshot(event)
    event.cancelled = True
    await audit(session, user_id, event, before, 'delete')
    await session.commit()

