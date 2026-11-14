from __future__ import annotations
from typing import Optional


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

