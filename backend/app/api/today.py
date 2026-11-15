from __future__ import annotations
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import Conflict, Event, PlanBlock, Task
from ..services.planning_service import active_preferences
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/today", tags=["planning"])


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def free_minutes_left(session, user_id, values, zone, *, now, start, end, planned) -> Optional[int]:
    """Free working minutes left in the day, minus blocks of still-open tasks.

    Only the calendar is needed, not the full planning state. Returns None when the
    calendar cannot be expanded (e.g. an invalid recurring event) so Today still loads.
    """
    from fastapi import HTTPException
    from ..services.planning_service import busy_with_sources, calendar_slots, day_overrides, planning_profile
    window_start = max(now, start)
    if end <= window_start:
        return 0
    _, windows = planning_profile(values)
    try:
        busy = [block for block, _ in await busy_with_sources(session, user_id, window_start, end, zone)]
    except HTTPException:
        return None
    slots = calendar_slots(window_start=window_start, window_end=end, zone=zone, windows=windows,
                           busy=busy, overrides=day_overrides(values))
    total = 0.0
    for slot in slots:
        minutes = (slot.end - slot.start).total_seconds() / 60
        for block in planned:
            overlap = (min(slot.end, _utc(block.end_at)) - max(slot.start, _utc(block.start_at))).total_seconds() / 60
            minutes -= max(0, overlap)
        total += max(0, minutes)
    return int(total)


CHECKIN_TIME = time(21, 0)  # PRD 5.6: end-of-day check-in, default 21:00 local


async def _checkin_window(session, user_id, now: datetime):
    values = await active_preferences(session, user_id)
    zone = ZoneInfo(values.get('timezone', {}).get('name', 'UTC'))
    local = now.astimezone(zone)
    start = datetime.combine(local.date(), time.min, tzinfo=zone).astimezone(timezone.utc)
    tomorrow = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    return local, start, tomorrow


async def unfinished_blocks(session, user_id, *, now: datetime, start: datetime, ids=None, lock=False):
    """Today's planned blocks that have started (or ended) but were not marked done, for open tasks."""
    query = (select(PlanBlock, Task.title).join(Task, and_(Task.id == PlanBlock.task_id, Task.user_id == user_id))
             .where(PlanBlock.user_id == user_id, PlanBlock.status == 'planned', PlanBlock.start_at >= start,
                    PlanBlock.start_at <= now, Task.status.in_(['open', 'blocked'])).order_by(PlanBlock.start_at))
    if ids is not None:
        query = query.where(PlanBlock.id.in_(ids))
    return list((await session.execute(query.with_for_update(of=PlanBlock) if lock else query)).all())


async def checkin_state(session, user_id, *, now: datetime) -> dict:
    local, start, _ = await _checkin_window(session, user_id, now)
    rows = await unfinished_blocks(session, user_id, now=now, start=start)
    return {'date': local.date(), 'due': local.time() >= CHECKIN_TIME and bool(rows),
            'checkin_time': CHECKIN_TIME.strftime('%H:%M'),
            'blocks': [{'id': str(block.id), 'task_id': str(block.task_id), 'title': title,
                        'start_at': block.start_at, 'end_at': block.end_at} for block, title in rows]}


@router.get('/checkin')
async def checkin(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    """End-of-day check-in (PRD 5.6): unfinished blocks with Move to tomorrow or Drop."""
    return await checkin_state(session, user_id, now=datetime.now(timezone.utc))


class CheckinAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['move_to_tomorrow', 'drop']
    block_ids: list[UUID] = Field(min_length=1, max_length=50)


@router.post('/checkin')
async def apply_checkin(payload: CheckinAction, session: AsyncSession = Depends(get_session),
                        user_id: UUID = Depends(current_user_id)) -> dict:
    return await apply_checkin_action(session, user_id, payload, now=datetime.now(timezone.utc))


async def apply_checkin_action(session, user_id, payload: CheckinAction, *, now: datetime) -> dict:
    from fastapi import HTTPException
    from ..models import ActivityEvent
    from ..services.domain_service import audit, lock_owner, snapshot
    from ..services.planning_service import rebuild_plan
    from ..services.task_service import drop_task
    await lock_owner(session, user_id)
    now = _utc(now)
    _, start, tomorrow = await _checkin_window(session, user_id, now)
    ids = set(payload.block_ids)
    rows = await unfinished_blocks(session, user_id, now=now, start=start, ids=ids, lock=True)
    if len(rows) != len(ids):
        raise HTTPException(status_code=409, detail='Some of those blocks are no longer unfinished today')
    session.add(ActivityEvent(user_id=user_id, type='checkin_' + payload.action[:24], occurred_at=now,
                              payload={'blocks': len(rows)}))
    if payload.action == 'drop':
        # Drop gives up on the task itself; each task is one undoable batch.
        batches, seen = [], set()
        for block, _ in rows:
            before = snapshot(block)
            block.status = 'missed'
            await audit(session, user_id, block, before, 'update')
            if block.task_id in seen:
                continue
            seen.add(block.task_id)
            task = (await session.execute(select(Task).where(Task.id == block.task_id, Task.user_id == user_id)
                                          .with_for_update())).scalar_one()
            batches.append(str(await drop_task(session, user_id, task)))
        await session.commit()
        return {'action': 'drop', 'dropped_tasks': len(seen), 'batch_ids': batches}
    for block, _ in rows:
        before = snapshot(block)
        block.status = 'moved'
        await audit(session, user_id, block, before, 'update')
    await session.flush()
    # Re-plan from the start of tomorrow, so the moved work lands tomorrow rather than late tonight.
    result = await rebuild_plan(session, user_id, now=max(now, tomorrow))
    moved_tasks = {str(block.task_id) for block, _ in rows}
    placed = [item for item in result['blocks'] if str(item.task_id) in moved_tasks]
    await session.commit()
    return {'action': 'move_to_tomorrow', 'moved': len(rows),
            'placed': [{'id': str(item.id), 'task_id': str(item.task_id), 'start_at': item.start_at,
                        'end_at': item.end_at} for item in placed],
            'unplaced_task_ids': [str(item) for item in result['unplaced_task_ids'] if str(item) in moved_tasks]}


@router.get("")
async def today(day: Optional[date] = Query(default=None), session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    values = await active_preferences(session, user_id)
    zone = ZoneInfo(values.get('timezone', {}).get('name', 'UTC'))
    selected = day or datetime.now(zone).date()
    start = datetime.combine(selected, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(selected + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    events = (await session.execute(select(Event).where(Event.user_id == user_id, Event.cancelled == False, Event.start_at < end, Event.end_at > start).order_by(Event.start_at))).scalars().all()
    blocks = (await session.execute(select(PlanBlock).where(PlanBlock.user_id == user_id, PlanBlock.start_at < end, PlanBlock.end_at > start).order_by(PlanBlock.start_at))).scalars().all()
    tasks = (await session.execute(select(Task).where(Task.user_id == user_id, Task.status.in_(["open", "blocked"]),
        Task.deadline_at < end).order_by(Task.pinned.desc(), Task.priority_score.desc(), Task.deadline_at))).scalars().all()
    conflicts = (await session.execute(select(Conflict).where(Conflict.user_id == user_id,
        Conflict.status == 'open').order_by(Conflict.deadline_at))).scalars().all()
    now = datetime.now(timezone.utc)
    rows = (await session.execute(select(Task.id, Task.title, Task.status).where(Task.user_id == user_id,
        Task.id.in_([block.task_id for block in blocks] or [None])))).all()
    titles = {row.id: row.title for row in rows}
    active = {row.id for row in rows if row.status in ('open', 'blocked')}
    free_min = await free_minutes_left(session, user_id, values, zone, now=now, start=start, end=end,
        planned=[block for block in blocks if block.status == 'planned' and block.task_id in active])
    next_block = next((block for block in blocks if block.status == 'planned' and
                       block.end_at.replace(tzinfo=timezone.utc) > now), None)
    return {
        "date": selected,
        "timezone": str(zone),
        "events": [{"id": str(item.id), "title": item.title, "start_at": item.start_at, "end_at": item.end_at, "location": item.location} for item in events],
        "plan_blocks": [{"id": str(item.id), "task_id": str(item.task_id), "title": titles.get(item.task_id), "start_at": item.start_at, "end_at": item.end_at, "status": item.status} for item in blocks],
        "free_min_left": free_min,
        "due_tasks": [{"id": str(item.id), "title": item.title, "deadline_at": item.deadline_at, "priority_score": item.priority_score, "priority_band": item.priority_band, "status": item.status, "why": item.priority_why, "overdue": bool(item.deadline_at and (item.deadline_at if item.deadline_at.tzinfo else item.deadline_at.replace(tzinfo=timezone.utc)) < now)} for item in tasks],
        "conflicts": [{"id": str(item.id), "deadline_at": item.deadline_at,
                       "needed_min": item.needed_min, "free_min": item.free_min, "task_ids": item.task_ids,
                       "shortfall_min": max(0, item.needed_min - item.free_min),
                       "options": item.options} for item in conflicts],
        "next": {"type": "plan_block", "id": str(next_block.id), "start_at": next_block.start_at, "end_at": next_block.end_at, "task_id": str(next_block.task_id), "title": titles.get(next_block.task_id)} if next_block else None,
    }

