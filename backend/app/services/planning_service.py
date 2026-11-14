"""Database-backed planning inputs shared by priority, schedule and capacity APIs."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update

from ..models import Conflict, Event, PlanBlock as StoredPlanBlock, Preference, Reminder, Routine, Task, TaskDependency
from .capacity_guard import CapacityConflict, CapacityTask, check_capacity
from .priority_engine import calculate_priority
from .scheduler import BusyBlock, SchedulableTask, build_free_slots, generate_plan, merge_slots
from .recurrence import expand_routine


DEFAULT_WORK_HOURS = {'start': '09:00', 'end': '18:00'}
# Effort used when a task arrives without an estimate (PRD F1 step 4), in minutes.
CATEGORY_DEFAULT_EFFORT = {'study': 120, 'work': 60, 'errand': 30, 'health': 45,
                           'social': 30, 'finance': 15, 'home': 30, 'other': 30}
CALIBRATION_MIN_SAMPLES = 10
CALIBRATION_WINDOW = 20


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _clock(value: str) -> time:
    return time.fromisoformat(value)


async def active_preferences(session, user_id: UUID) -> dict:
    rows = (await session.execute(select(Preference).where(Preference.user_id == user_id,
        Preference.status == 'active'))).scalars().all()
    return {row.key: row.value for row in rows}


def planning_profile(values: dict) -> tuple[ZoneInfo, list[tuple[time, time]]]:
    """Timezone and the daily working windows that make up planning supply.

    Working hours are the supply of free time. Focus windows only describe when the
    user concentrates best; they do not shrink the working day.
    """
    timezone_name = values.get('timezone', {}).get('name', 'UTC')
    zone = ZoneInfo(timezone_name)
    work = values.get('work_hours', DEFAULT_WORK_HOURS)
    return zone, [(_clock(work['start']), _clock(work['end']))]


def day_overrides(values: dict) -> dict[date, list[tuple[time, time]]]:
    dates = values.get('work_hours_overrides', {}).get('dates', {})
    return {date.fromisoformat(day): [(_clock(hours['start']), _clock(hours['end']))]
            for day, hours in dates.items()}


def calendar_slots(*, window_start: datetime, window_end: datetime, zone: ZoneInfo,
                   windows: list[tuple[time, time]], busy: list[BusyBlock],
                   overrides: dict[date, list[tuple[time, time]]] | None = None) -> list[BusyBlock]:
    """Create free UTC slots from local working windows and persisted events."""
    local_start = _utc(window_start).astimezone(zone)
    local_end = _utc(window_end).astimezone(zone)
    day = local_start.date()
    slots: list[BusyBlock] = []
    while day <= local_end.date():
        for start_clock, end_clock in (overrides or {}).get(day, windows):
            start = datetime.combine(day, start_clock, tzinfo=zone).astimezone(timezone.utc)
            end = datetime.combine(day, end_clock, tzinfo=zone).astimezone(timezone.utc)
            if end > start:
                slots.extend(build_free_slots(window_start=max(start, _utc(window_start)),
                    window_end=min(end, _utc(window_end)), working_hours=[(0, 24)],
                    busy=busy))
        day += timedelta(days=1)
    return merge_slots(slots)


async def busy_for_window(session, user_id: UUID, start: datetime, end: datetime, zone: ZoneInfo) -> list[BusyBlock]:
    return [block for block, _ in await busy_with_sources(session, user_id, start, end, zone)]


async def busy_with_sources(session, user_id: UUID, start: datetime, end: datetime,
                            zone: ZoneInfo) -> list[tuple[BusyBlock, dict]]:
    """Busy time with the item that causes it (used to simulate moving routines)."""
    events = list((await session.execute(select(Event).where(Event.user_id == user_id,
        Event.cancelled == False, Event.start_at < end,
        (Event.end_at > start) | Event.rrule.is_not(None)))).scalars())
    from dateutil.rrule import rrulestr
    busy: list[tuple[BusyBlock, dict]] = []
    for event in events:
        begin, finish = _utc(event.start_at), _utc(event.end_at)
        source = {'type': 'event', 'id': str(event.id), 'title': event.title}
        if not event.rrule:
            busy.append((BusyBlock(begin, finish), source))
            continue
        duration = finish - begin
        try:
            rule = rrulestr(event.rrule, dtstart=begin.astimezone(zone))
        except (TypeError, ValueError) as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail='Invalid recurring event; repair it before planning') from exc
        for index, occurrence in enumerate(rule.xafter(start - duration, inc=True)):
            if occurrence >= end:
                break
            if index >= 500:
                from fastapi import HTTPException
                raise HTTPException(status_code=409, detail='Too many recurring event instances')
            busy.append((BusyBlock(_utc(occurrence), _utc(occurrence) + duration), source))
    routines = list((await session.execute(select(Routine).where(Routine.user_id == user_id))).scalars())
    for routine in routines:
        try:
            instances = expand_routine(routine.rrule, routine.start_time, routine.duration_min,
                datetime.fromisoformat(routine.anchor_date).date(), start, end, str(zone), routine.overrides)
        except (TypeError, ValueError) as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail='Invalid routine data; repair it before planning') from exc
        for item in instances:
            busy.append((BusyBlock(_utc(item['start_at']), _utc(item['end_at'])),
                         {'type': 'routine', 'id': str(routine.id), 'title': routine.title,
                          'movable': routine.movable, 'original_start': item['original_start'],
                          'duration_min': routine.duration_min}))
    return busy


def minutes_until(slots: list[BusyBlock], deadline: datetime) -> int:
    end = _utc(deadline)
    return sum(max(0, int((min(slot.end, end) - slot.start).total_seconds() / 60))
               for slot in slots if slot.start < end)


async def calibration_factors(session, user_id, values: dict | None = None) -> dict[str, float]:
    """Median actual/estimated effort per category over the last 20 completions.

    Returns no factors (so 1.0 applies) during cold start or when the user turned
    estimate padding off.
    """
    if values is None:
        values = await active_preferences(session, user_id)
    if not values.get('estimate_padding', {'enabled': True}).get('enabled', True):
        return {}
    rows = (await session.execute(select(Task.category, Task.effort_est_min, Task.effort_actual_min)
        .where(Task.user_id == user_id, Task.status == 'done', Task.effort_actual_min.is_not(None),
               Task.effort_actual_min > 0, Task.effort_est_min > 0)
        .order_by(Task.completed_at))).all()
    if len(rows) < CALIBRATION_MIN_SAMPLES:
        return {}
    ratios: dict[str, list[float]] = defaultdict(list)
    for category, estimate, actual in rows:
        ratios[category].append(actual / estimate)
    return {category: round(max(0.5, min(3.0, median(values[-CALIBRATION_WINDOW:]))), 2)
            for category, values in ratios.items()}


def effective_effort(task: Task, factors: dict[str, float], done_min: int = 0) -> int:
    """Remaining calibrated effort in minutes (never below 5 for open work)."""
    calibrated = round(task.effort_est_min * factors.get(task.category, 1.0))
    return max(5, calibrated - done_min)


async def done_minutes(session, user_id) -> dict[UUID, int]:
    rows = (await session.execute(select(StoredPlanBlock.task_id, StoredPlanBlock.start_at, StoredPlanBlock.end_at)
        .join(Task, Task.id == StoredPlanBlock.task_id)
        .where(StoredPlanBlock.user_id == user_id, StoredPlanBlock.status == 'done',
               Task.status.in_(['open', 'blocked'])))).all()
    totals: dict[UUID, int] = defaultdict(int)
    for task_id, start, end in rows:
        totals[task_id] += int((_utc(end) - _utc(start)).total_seconds() / 60)
    return totals


@dataclass
class PlanningState:
    now: datetime
    end: datetime
    zone: ZoneInfo
    tasks: list[Task]
    slots: list[BusyBlock]
    busy: list[tuple[BusyBlock, dict]]
    efforts: dict[UUID, int]
    factors: dict[str, float]
    windows: list[tuple[time, time]] = field(default_factory=list)
    overrides: dict[date, list[tuple[time, time]]] = field(default_factory=dict)


async def load_state(session, user_id, *, now: datetime, days: int, extra_busy=(),
                     overrides: dict | None = None) -> PlanningState:
    now = _utc(now)
    end = now + timedelta(days=days)
    values = await active_preferences(session, user_id)
    zone, windows = planning_profile(values)
    merged_overrides = {**day_overrides(values), **(overrides or {})}
    busy = await busy_with_sources(session, user_id, now, end, zone)
    busy += [(block, {'type': 'constraint'}) for block in extra_busy]
    slots = calendar_slots(window_start=now, window_end=end, zone=zone, windows=windows,
                           busy=[block for block, _ in busy], overrides=merged_overrides)
    tasks = list((await session.execute(select(Task).where(Task.user_id == user_id,
        Task.status.in_(['open', 'blocked'])).order_by(Task.id))).scalars())
    factors = await calibration_factors(session, user_id, values)
    progress = await done_minutes(session, user_id)
    efforts = {task.id: effective_effort(task, factors, progress.get(task.id, 0)) for task in tasks}
    return PlanningState(now, end, zone, tasks, slots, busy, efforts, factors, windows, merged_overrides)


def evaluate(state: PlanningState, *, slots: list[BusyBlock] | None = None,
             deadlines: dict[UUID, datetime] | None = None):
    """Run scheduler and Capacity Guard in memory: (blocks, unplaced, conflicts)."""
    slots = state.slots if slots is None else slots
    deadlines = deadlines or {}

    def deadline_of(task):
        value = deadlines.get(task.id, task.deadline_at)
        return _utc(value) if value is not None else None

    schedulable = [SchedulableTask(str(task.id), state.efforts[task.id],
        deadline_of(task) or state.end, task.priority_score, task.status == 'blocked')
        for task in state.tasks]
    blocks, unplaced = generate_plan(tasks=schedulable, slots=slots)
    checked = [task for task in state.tasks if deadline_of(task) is not None
               and state.now < deadline_of(task) <= state.end]
    supply = {deadline_of(task): minutes_until(slots, deadline_of(task)) for task in checked}
    conflicts = check_capacity(tasks=[CapacityTask(str(task.id), task.title, state.efforts[task.id],
        deadline_of(task), task.priority_score, not task.pinned) for task in checked],
        free_minutes_until=supply)
    return blocks, unplaced, conflicts


async def recalculate_priorities(session, user_id: UUID, now: datetime | None = None,
                                 horizon_days: int = 7) -> list[Task]:
    from .domain_service import lock_owner
    await lock_owner(session, user_id)
    now = _utc(now or datetime.now(timezone.utc))
    state = await load_state(session, user_id, now=now, days=horizon_days)
    dependencies = list((await session.execute(select(TaskDependency).where(
        TaskDependency.user_id == user_id))).scalars())
    dependent_counts = defaultdict(int)
    open_ids = {task.id for task in state.tasks}
    for edge in dependencies:
        if edge.task_id in open_ids:
            dependent_counts[edge.depends_on_task_id] += 1
    total_free = sum(int((slot.end - slot.start).total_seconds() / 60) for slot in state.slots) / 60
    for task in state.tasks:
        free_hours = minutes_until(state.slots, task.deadline_at) / 60 if task.deadline_at else total_free
        result = calculate_priority(now=now, deadline=_utc(task.deadline_at) if task.deadline_at else None,
            effort_min=state.efforts[task.id], importance=task.importance,
            blocking_count=dependent_counts[task.id], created_at=_utc(task.created_at),
            free_working_hours=free_hours)
        task.priority_score, task.priority_band = result.score, result.band
        factor = state.factors.get(task.category, 1.0)
        why = result.why
        if task.pinned:
            why = 'Pinned to the top'
        elif task.status == 'blocked':
            why = 'Blocked by an unfinished task'
        elif factor != 1.0 and task.deadline_at and _utc(task.deadline_at) > now:
            why += f' ({task.effort_est_min / 60:g} h x {factor:g} your {task.category} factor)'
        task.priority_why = why[:200]
        task.priority_breakdown = {
            'urgency': round(result.urgency, 3), 'importance': round(result.importance, 3),
            'blocking': round(result.blocking, 3), 'staleness': round(result.staleness, 3),
            'weights': {'urgency': 0.45, 'importance': 0.30, 'blocking': 0.15, 'staleness': 0.10},
            'free_hours_before_deadline': round(free_hours, 2),
            'effort_min': state.efforts[task.id], 'estimate_min': task.effort_est_min,
            'calibration_factor': factor, 'blocks_count': dependent_counts[task.id],
        }
    await session.flush()
    return state.tasks


async def persist_conflicts(session, user_id, conflicts: list[CapacityConflict]) -> list[Conflict]:
    """Replace open conflicts, keeping the id of one whose deadline is unchanged."""
    existing = {(_utc(row.deadline_at)): row for row in (await session.execute(select(Conflict).where(
        Conflict.user_id == user_id, Conflict.status == 'open'))).scalars()}
    stored = []
    for conflict in conflicts:
        row = existing.pop(_utc(conflict.deadline), None)
        if row is None:
            row = Conflict(user_id=user_id, deadline_at=conflict.deadline, status='open')
            session.add(row)
        row.needed_min, row.free_min = conflict.needed_min, conflict.free_min
        row.task_ids, row.options = conflict.task_ids, conflict.options
        stored.append(row)
    for row in existing.values():
        await session.delete(row)
    await session.flush()
    return stored


async def detect_conflicts(session, user_id, *, now: datetime | None = None, days: int = 7) -> list[Conflict]:
    """Capacity Guard after a change, without rewriting the plan (PRD F2.4)."""
    state = await load_state(session, user_id, now=now or datetime.now(timezone.utc), days=days)
    _, _, conflicts = evaluate(state)
    return await persist_conflicts(session, user_id, conflicts)


async def rebuild_plan(session, user_id: UUID, *, now: datetime | None = None,
                       days: int = 7, extra_busy=()) -> dict:
    if not 1 <= days <= 14:
        raise ValueError('days must be between 1 and 14')
    from .domain_service import lock_owner
    await lock_owner(session, user_id)
    now = _utc(now or datetime.now(timezone.utc))
    await recalculate_priorities(session, user_id, now, days)
    state = await load_state(session, user_id, now=now, days=days, extra_busy=extra_busy)
    blocks, unplaced, conflicts = evaluate(state)
    # A rebuild replaces only future, still-planned work; history is preserved.
    await session.execute(delete(StoredPlanBlock).where(StoredPlanBlock.user_id == user_id,
        StoredPlanBlock.status == 'planned', StoredPlanBlock.end_at >= now))
    await session.execute(update(Reminder).where(Reminder.user_id == user_id,
        Reminder.kind == 'plan_block', Reminder.status == 'pending').values(status='cancelled'))
    titles = {str(task.id): task.title for task in state.tasks}
    stored = []
    for block in blocks:
        item = StoredPlanBlock(user_id=user_id, task_id=UUID(block.task_id), start_at=block.start,
            end_at=block.end, plan_date=block.start.astimezone(state.zone).replace(hour=0, minute=0,
            second=0, microsecond=0).astimezone(timezone.utc))
        session.add(item)
        stored.append(item)
        if block.start > now:
            minutes = int((block.end - block.start).total_seconds() / 60)
            session.add(Reminder(user_id=user_id, item_type='task', item_id=UUID(block.task_id),
                kind='plan_block', fire_at=block.start, status='pending',
                message=f'Time for {titles[block.task_id]}: {minutes} min block starts now.'))
    rows = await persist_conflicts(session, user_id, conflicts)
    await session.flush()
    return {'blocks': stored, 'unplaced_task_ids': [item.id for item in unplaced],
            'conflicts': conflicts, 'conflict_rows': rows, 'timezone': str(state.zone)}


async def free_windows(session, user_id, *, task_id: UUID | None, now: datetime | None = None,
                       days: int = 7) -> list[BusyBlock]:
    """Free working time, treating other tasks' planned blocks as busy."""
    now = _utc(now or datetime.now(timezone.utc))
    state = await load_state(session, user_id, now=now, days=days)
    planned = (await session.execute(select(StoredPlanBlock).where(StoredPlanBlock.user_id == user_id,
        StoredPlanBlock.status == 'planned', StoredPlanBlock.end_at > now))).scalars().all()
    busy = [block for block, _ in state.busy] + [BusyBlock(_utc(row.start_at), _utc(row.end_at))
        for row in planned if row.task_id != task_id]
    return calendar_slots(window_start=now, window_end=state.end, zone=state.zone,
                          windows=state.windows, busy=busy, overrides=state.overrides)


async def next_free_slots(session, user_id, *, task_id: UUID | None, duration_min: int,
                          now: datetime | None = None, count: int = 3, days: int = 7) -> list[dict]:
    """Earliest free windows that fit `duration_min` (Reschedule, PRD F3)."""
    output = []
    for slot in await free_windows(session, user_id, task_id=task_id, now=now, days=days):
        if (slot.end - slot.start) >= timedelta(minutes=duration_min):
            output.append({'start_at': slot.start, 'end_at': slot.start + timedelta(minutes=duration_min)})
            if len(output) == count:
                break
    return output
