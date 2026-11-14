from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import ActionLog, Preference, Routine
from ..schemas_preferences import PreferenceUpdate, RoutineCreate
from ..services.domain_service import audit, snapshot, sync_all_reminders
from ..services.recurrence import expand_routine
from datetime import date, datetime, timezone
from pydantic import BaseModel, AwareDatetime, Field

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class RoutineInstanceEdit(BaseModel):
    original_start: AwareDatetime
    start_at: AwareDatetime
    duration_min: int = Field(ge=5, le=600)
    cancelled: bool = False


@router.get('/routines/{routine_id}/instances')
async def routine_instances(routine_id: UUID, start: datetime, end: datetime, tz: str='UTC',
    session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    row = (await session.execute(select(Routine).where(Routine.id == routine_id, Routine.user_id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Routine not found')
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(status_code=422, detail='Use timezone-aware dates')
    try:
        return expand_routine(row.rrule, row.start_time, row.duration_min, date.fromisoformat(row.anchor_date), start, end, tz, row.overrides)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch('/routines/{routine_id}/instance')
async def move_instance(routine_id: UUID, payload: RoutineInstanceEdit, tz: str='UTC',
    session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    row = (await session.execute(select(Routine).where(Routine.id == routine_id, Routine.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Routine not found')
    from datetime import timedelta
    try:
        candidates = expand_routine(row.rrule, row.start_time, row.duration_min,
            date.fromisoformat(row.anchor_date), payload.original_start, payload.original_start + timedelta(seconds=1), tz)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not candidates:
        raise HTTPException(status_code=404, detail='Routine instance does not exist')
    before = snapshot(row)
    edits = dict(row.overrides or {})
    edits[payload.original_start.astimezone(timezone.utc).isoformat()] = payload.model_dump(mode='json')
    row.overrides = edits
    action = await audit(session, user_id, row, before, 'update')
    await session.commit()
    return {'routine': snapshot(row), 'action_id': str(action.id)}


@router.get("")
async def list_preferences(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> list[dict]:
    rows = (await session.execute(select(Preference).where(Preference.user_id == user_id).order_by(Preference.key))).scalars().all()
    return [{"id": str(row.id), "key": row.key, "value": row.value, "source": row.source, "confidence": row.confidence, "status": row.status} for row in rows]


@router.patch('')
@router.post("", status_code=status.HTTP_201_CREATED)
async def set_preference(payload: PreferenceUpdate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    row = (await session.execute(select(Preference).where(Preference.user_id == user_id,
        Preference.key == payload.key).with_for_update())).scalar_one_or_none()
    before = snapshot(row) if row else None
    if row is None:
        row = Preference(user_id=user_id, **payload.model_dump())
        session.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    await session.flush()
    action = await audit(session, user_id, row, before, 'create' if before is None else 'update')
    await session.commit()
    await session.refresh(row)
    return {"id": str(row.id), "key": row.key, "value": row.value, "source": row.source, "confidence": row.confidence, "status": row.status}


@router.post('/{preference_id}/accept')
async def accept_preference(preference_id: UUID, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    row = (await session.execute(select(Preference).where(Preference.id == preference_id,
        Preference.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Preference not found')
    before = snapshot(row)
    row.status = 'active'
    action = await audit(session, user_id, row, before, 'accept')
    await session.commit()
    return {'preference': snapshot(row), 'action_id': str(action.id)}


@router.delete("/{preference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(preference_id: UUID, confirmed: bool=False, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> None:
    if not confirmed:
        raise HTTPException(status_code=409, detail='Explicit confirmation required')
    row = (await session.execute(select(Preference).where(Preference.id == preference_id,
        Preference.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Preference not found")
    session.add(ActionLog(user_id=user_id, entity='preferences', entity_id=row.id,
        action_type='delete', before=snapshot(row), after=None))
    await session.delete(row)
    await session.flush()
    await sync_all_reminders(session, user_id)
    await session.commit()


@router.get("/routines")
async def list_routines(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> list[dict]:
    rows = (await session.execute(select(Routine).where(Routine.user_id == user_id).order_by(Routine.start_time))).scalars().all()
    return [{"id": str(row.id), "title": row.title, "rrule": row.rrule, "start_time": row.start_time, "duration_min": row.duration_min, "movable": row.movable} for row in rows]


@router.post("/routines", status_code=status.HTTP_201_CREATED)
async def create_routine(payload: RoutineCreate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    row = Routine(user_id=user_id, **payload.model_dump())
    session.add(row)
    await session.flush()
    await audit(session, user_id, row, None, 'create')
    await session.commit()
    await session.refresh(row)
    return {"id": str(row.id), "title": row.title, "rrule": row.rrule, "start_time": row.start_time, "duration_min": row.duration_min, "movable": row.movable}


@router.put('/routines/{routine_id}')
async def replace_routine(routine_id: UUID, payload: RoutineCreate,
    session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    row = (await session.execute(select(Routine).where(Routine.id == routine_id,
        Routine.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Routine not found')
    before = snapshot(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.overrides = {}
    action = await audit(session, user_id, row, before, 'update')
    await session.commit()
    return {'routine': snapshot(row), 'action_id': str(action.id)}


@router.delete('/routines/{routine_id}', status_code=204)
async def delete_routine(routine_id: UUID, confirmed: bool=False,
    session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    if not confirmed:
        raise HTTPException(status_code=409, detail='Explicit confirmation required')
    row = (await session.execute(select(Routine).where(Routine.id == routine_id,
        Routine.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Routine not found')
    session.add(ActionLog(user_id=user_id, entity='routines', entity_id=row.id,
        action_type='delete', before=snapshot(row), after=None))
    await session.delete(row)
    await session.commit()

