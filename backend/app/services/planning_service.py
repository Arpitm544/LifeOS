"""Database-backed planning inputs shared by priority, schedule and capacity APIs."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from ..models import Conflict, Event, PlanBlock as StoredPlanBlock, Preference, Routine, Task, TaskDependency
from .capacity_guard import CapacityTask, check_capacity
from .priority_engine import calculate_priority
from .scheduler import BusyBlock, SchedulableTask, build_free_slots, generate_plan
from .recurrence import expand_routine


DEFAULT_WORK_HOURS = {'start': '09:00', 'end': '18:00'}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _clock(value: str) -> time:
    return time.fromisoformat(value)


async def active_preferences(session, user_id: UUID) -> dict:
    rows = (await session.execute(select(Preference).where(Preference.user_id == user_id,
        Preference.status == 'active'))).scalars().all()
    return {row.key: row.value for row in rows}


def planning_profile(values: dict) -> tuple[ZoneInfo, list[tuple[time, time]]]:
    timezone_name = values.get('timezone', {}).get('name', 'UTC')
    zone = ZoneInfo(timezone_name)
    work = values.get('work_hours', DEFAULT_WORK_HOURS)
    windows = values.get('focus_windows', {}).get('windows') or [(work['start'], work['end'])]
    return zone, [(_clock(start), _clock(end)) for start, end in windows]


def calendar_slots(*, window_start: datetime, window_end: datetime, zone: ZoneInfo,
                   windows: list[tuple[time, time]], busy: list[BusyBlock]) -> list[BusyBlock]:
    """Create free UTC slots from local working/focus windows and persisted events."""
    local_start = _utc(window_start).astimezone(zone)
    local_end = _utc(window_end).astimezone(zone)
    day = local_start.date()
    slots: list[BusyBlock] = []
    while day <= local_end.date():
        for start_clock, end_clock in windows:
            start = datetime.combine(day, start_clock, tzinfo=zone).astimezone(timezone.utc)
            end = datetime.combine(day, end_clock, tzinfo=zone).astimezone(timezone.utc)
            if end > start:
                slots.extend(build_free_slots(window_start=max(start, _utc(window_start)),
                    window_end=min(end, _utc(window_end)), working_hours=[(0, 24)],
                    busy=busy))
        day += timedelta(days=1)
    return sorted(slots, key=lambda item: item.start)


async def busy_for_window(session, user_id: UUID, start: datetime, end: datetime, zone: ZoneInfo) -> list[BusyBlock]:
    events = list((await session.execute(select(Event).where(Event.user_id == user_id,
        Event.cancelled == False, Event.start_at < end, Event.end_at > start))).scalars())
    busy = [BusyBlock(_utc(event.start_at), _utc(event.end_at)) for event in events]
    routines = list((await session.execute(select(Routine).where(Routine.user_id == user_id))).scalars())
    for routine in routines:
        try:
            instances = expand_routine(routine.rrule, routine.start_time, routine.duration_min,
                datetime.fromisoformat(routine.anchor_date).date(), start, end, str(zone), routine.overrides)
        except (TypeError, ValueError):
            # Invalid historical data must not make planning unsafe; it is surfaced
            # by routine validation/editing instead of becoming free time.
            continue
        busy.extend(BusyBlock(_utc(item['start_at']), _utc(item['end_at'])) for item in instances)
    return busy


def minutes_until(slots: list[BusyBlock], deadline: datetime) -> int:
    end = _utc(deadline)
    return sum(max(0, int((min(slot.end, end) - slot.start).total_seconds() / 60))
               for slot in slots if slot.start < end)


async def recalculate_priorities(session, user_id: UUID, now: datetime | None = None,
                                 horizon_days: int = 7) -> list[Task]:
    now = _utc(now or datetime.now(timezone.utc))
    values = await active_preferences(session, user_id)
    zone, windows = planning_profile(values)
    end = now + timedelta(days=horizon_days)
    busy = await busy_for_window(session, user_id, now, end, zone)
    slots = calendar_slots(window_start=now, window_end=end, zone=zone, windows=windows, busy=busy)
    tasks = list((await session.execute(select(Task).where(Task.user_id == user_id,
        Task.status.in_(['open', 'blocked'])).with_for_update())).scalars())
    dependencies = list((await session.execute(select(TaskDependency).where(
        TaskDependency.user_id == user_id))).scalars())
    dependent_counts = defaultdict(int)
    for edge in dependencies:
        dependent_counts[edge.depends_on_task_id] += 1
    for task in tasks:
        free_hours = (minutes_until(slots, task.deadline_at) / 60 if task.deadline_at else
                      sum(int((slot.end - slot.start).total_seconds() / 60) for slot in slots) / 60)
        result = calculate_priority(now=now, deadline=_utc(task.deadline_at) if task.deadline_at else None,
            effort_min=task.effort_est_min, importance=task.importance,
            blocking_count=dependent_counts[task.id], created_at=_utc(task.created_at),
            free_working_hours=free_hours)
        task.priority_score, task.priority_band = result.score, result.band
    await session.flush()
    return tasks


async def rebuild_plan(session, user_id: UUID, *, now: datetime | None = None,
                       days: int = 7) -> dict:
    if not 1 <= days <= 14:
        raise ValueError('days must be between 1 and 14')
    now = _utc(now or datetime.now(timezone.utc))
    end = now + timedelta(days=days)
    values = await active_preferences(session, user_id)
    zone, windows = planning_profile(values)
    tasks = await recalculate_priorities(session, user_id, now, days)
    busy = await busy_for_window(session, user_id, now, end, zone)
    slots = calendar_slots(window_start=now, window_end=end, zone=zone, windows=windows, busy=busy)
    schedulable = [SchedulableTask(str(task.id), task.effort_est_min,
        _utc(task.deadline_at) if task.deadline_at else end, task.priority_score,
        task.status == 'blocked') for task in tasks]
    blocks, unplaced = generate_plan(tasks=schedulable, slots=slots)
    # A rebuild replaces only future, still-planned work; history is preserved.
    await session.execute(delete(StoredPlanBlock).where(StoredPlanBlock.user_id == user_id,
        StoredPlanBlock.status == 'planned', StoredPlanBlock.end_at >= now))
    stored = []
    for block in blocks:
        item = StoredPlanBlock(user_id=user_id, task_id=UUID(block.task_id), start_at=block.start,
            end_at=block.end, plan_date=block.start.astimezone(zone).replace(hour=0, minute=0,
            second=0, microsecond=0).astimezone(timezone.utc))
        session.add(item)
        stored.append(item)
    deadlines = {_utc(task.deadline_at) for task in tasks if task.deadline_at is not None}
    supply = {deadline: minutes_until(slots, deadline) for deadline in deadlines}
    conflicts = check_capacity(tasks=[CapacityTask(str(task.id), task.title, task.effort_est_min,
        _utc(task.deadline_at), task.priority_score, not task.pinned) for task in tasks if task.deadline_at],
        free_minutes_until=supply)
    await session.execute(delete(Conflict).where(Conflict.user_id == user_id, Conflict.status == 'open'))
    for conflict in conflicts:
        session.add(Conflict(user_id=user_id, deadline_at=conflict.deadline, needed_min=conflict.needed_min,
            free_min=conflict.free_min, task_ids=conflict.task_ids, options=conflict.options, status='open'))
    await session.flush()
    return {'blocks': stored, 'unplaced_task_ids': [item.id for item in unplaced],
            'conflicts': conflicts, 'timezone': str(zone)}
