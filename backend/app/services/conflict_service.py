"""Capacity Guard options (PRD 5.4): simulate each fix with the scheduler, then apply one."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from ..models import Conflict, Preference, Routine, Task
from .domain_service import audit, snapshot
from .planning_service import busy_with_sources, calendar_slots, evaluate, load_state, rebuild_plan
from .scheduler import BusyBlock

EXTEND_UNTIL = time(21, 0)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _shortfall(conflicts, deadline: datetime) -> int:
    for item in conflicts:
        if _utc(item.deadline) == _utc(deadline):
            return item.shortfall_min
    return 0


def _in_quiet(moment: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= moment < end
    return moment >= start or moment < end  # overnight, e.g. 22:30-07:30


def extension_limit(work_end: time, quiet_start: time, quiet_end: time) -> time:
    """Latest time up to 21:00 reachable after work without entering quiet hours."""
    cursor = datetime.combine(datetime.min.date(), work_end)
    stop = datetime.combine(datetime.min.date(), EXTEND_UNTIL)
    while cursor < stop and not _in_quiet(cursor.time(), quiet_start, quiet_end):
        cursor += timedelta(minutes=15)
    return min(cursor, stop).time() if cursor > datetime.combine(datetime.min.date(), work_end) else work_end


def free_destination(block: BusyBlock, deadline: datetime, busy: list[BusyBlock]) -> datetime | None:
    """Same time of day on the first day after the deadline that is not already booked."""
    length = block.end - block.start
    first = (deadline - block.start).days + 1
    for offset in range(first, first + 7):
        start = block.start + timedelta(days=offset)
        if start < deadline:
            continue
        if not any(other.start < start + length and start < other.end for other in busy):
            return start
    return None


def _least_important(task):
    # Deterministic: lowest score, then importance, then latest deadline, then title.
    return (task.priority_score, task.importance, -_utc(task.deadline_at).timestamp() if task.deadline_at else 0, task.title)


def _preview(blocks, titles, until: datetime) -> list[dict]:
    return [{'task_id': block.task_id, 'title': titles.get(block.task_id, 'Task'),
             'start_at': block.start.isoformat(), 'end_at': block.end.isoformat()}
            for block in blocks if block.start < until][:12]


async def simulate_options(session, user_id, conflict: Conflict, *, now: datetime | None = None) -> list[dict]:
    """Return up to three simulated outcomes. Nothing is written."""
    now = _utc(now or datetime.now(timezone.utc))
    deadline = _utc(conflict.deadline_at)
    days = max(1, min(14, (deadline - now).days + 1))
    state = await load_state(session, user_id, now=now, days=days)
    titles = {str(task.id): task.title for task in state.tasks}
    involved = [task for task in state.tasks if str(task.id) in set(conflict.task_ids)]
    options: list[dict] = []

    # 1. Extend working hours to 21:00 (bounded by quiet hours) on days before D.
    prefs = {row.key: row.value for row in (await session.execute(select(Preference).where(
        Preference.user_id == user_id, Preference.status == 'active'))).scalars()}
    quiet = prefs.get('quiet_hours', {'start': '22:30', 'end': '07:30'})
    quiet_start, quiet_end = time.fromisoformat(quiet['start']), time.fromisoformat(quiet['end'])
    overrides = dict(state.overrides)
    local_day = now.astimezone(state.zone).date()
    extended_days, limit = [], None
    while local_day <= deadline.astimezone(state.zone).date():
        windows = overrides.get(local_day, state.windows)
        start, end = windows[0][0], max(end for _, end in windows)
        day_limit = extension_limit(end, quiet_start, quiet_end)
        if day_limit > end:
            overrides[local_day] = [(start, day_limit)]
            extended_days.append(local_day.isoformat())
            limit = day_limit if limit is None else min(limit, day_limit)
        local_day += timedelta(days=1)
    if extended_days:
        slots = calendar_slots(window_start=now, window_end=state.end, zone=state.zone, windows=state.windows,
                               busy=[block for block, _ in state.busy], overrides=overrides)
        blocks, _, conflicts = evaluate(state, slots=slots)
        options.append({'type': 'extend_hours', 'resolves': _shortfall(conflicts, deadline) == 0,
                        'remaining_shortfall_min': _shortfall(conflicts, deadline),
                        'change': {'dates': extended_days, 'end': limit.strftime('%H:%M'),
                                   'ends': {day: overrides[datetime.fromisoformat(day).date()][0][1].strftime('%H:%M')
                                            for day in extended_days}},
                        'description': f"Work until {limit.strftime('%H:%M')} on {len(extended_days)} day(s) before the deadline",
                        'preview': _preview(blocks, titles, deadline)})

    # 2. Move a flexible item: a movable routine instance, else the lowest-priority task.
    movable = [(block, source) for block, source in state.busy
               if source.get('type') == 'routine' and source.get('movable') and block.start < deadline and block.end > now]
    best = None
    later = await busy_with_sources(session, user_id, deadline, deadline + timedelta(days=9), state.zone) if movable else []
    for block, source in sorted(movable, key=lambda item: -(item[0].end - item[0].start)):
        busy = [b for b, s in state.busy if not (s is source and b == block)]
        moved_to = free_destination(block, deadline, [b for b, _ in later] + busy)
        if moved_to is None:
            continue  # no free slot at the same time in the week after the deadline
        busy.append(BusyBlock(moved_to, moved_to + (block.end - block.start)))
        slots = calendar_slots(window_start=now, window_end=state.end, zone=state.zone, windows=state.windows,
                               busy=busy, overrides=state.overrides)
        blocks, _, conflicts = evaluate(state, slots=slots)
        remaining = _shortfall(conflicts, deadline)
        if best is None or remaining < best['remaining_shortfall_min']:
            best = {'type': 'move_flexible', 'resolves': remaining == 0, 'remaining_shortfall_min': remaining,
                    'change': {'routine_id': source['id'], 'original_start': source['original_start'],
                               'start_at': moved_to.isoformat(), 'duration_min': source['duration_min']},
                    'description': f"Move {source['title']} to {moved_to.astimezone(state.zone):%a %H:%M}",
                    'preview': _preview(blocks, titles, deadline)}
    flexible = sorted((task for task in involved if not task.pinned), key=_least_important)
    if flexible and (best is None or not best['resolves']):
        task = flexible[0]
        new_deadline = deadline + timedelta(days=1)
        blocks, _, conflicts = evaluate(state, deadlines={task.id: new_deadline})
        remaining = _shortfall(conflicts, deadline)
        candidate = {'type': 'move_flexible', 'resolves': remaining == 0, 'remaining_shortfall_min': remaining,
                     'change': {'task_id': str(task.id), 'deadline_at': new_deadline.isoformat()},
                     'description': f"Move {task.title} to {new_deadline.astimezone(state.zone):%a %d %b}",
                     'preview': _preview(blocks, titles, deadline)}
        if best is None or remaining < best['remaining_shortfall_min']:
            best = candidate
    if best:
        options.append(best)

    # 3. Renegotiate: keep the plan, flag the task that will miss D, draft a message.
    if involved:
        at_risk = min(involved, key=_least_important)
        blocks, _, conflicts = evaluate(state)
        when = deadline.astimezone(state.zone).strftime('%A')
        options.append({'type': 'renegotiate', 'resolves': False,
                        'remaining_shortfall_min': _shortfall(conflicts, deadline),
                        'change': {'task_id': str(at_risk.id)},
                        'description': f'Keep the plan and ask for more time on {at_risk.title}',
                        'draft_message': (f"Hi, I'm running short on time for \"{at_risk.title}\", due {when}. "
                                          f"Could I have until {(deadline + timedelta(days=2)).astimezone(state.zone):%A}? "
                                          "I want to hand in work I'm proud of. Thank you!"),
                        'preview': _preview(blocks, titles, deadline)})
    return options


async def resolve(session, user_id, conflict: Conflict, option_type: str, *, now: datetime | None = None) -> dict:
    """Apply one simulated option as a single undoable batch, then re-plan."""
    now = _utc(now or datetime.now(timezone.utc))
    options = {item['type']: item for item in await simulate_options(session, user_id, conflict, now=now)}
    if option_type not in options:
        raise HTTPException(status_code=409, detail='That option is not available for this conflict any more')
    option = options[option_type]
    batch_id = uuid4()
    change = option['change']
    # Audit after re-planning: the rebuild re-scores priorities, and Undo compares
    # each row with its logged "after" snapshot.
    pending_audits: list[tuple[object, dict | None, str]] = []
    if option_type == 'extend_hours':
        row = (await session.execute(select(Preference).where(Preference.user_id == user_id,
            Preference.key == 'work_hours_overrides').with_for_update())).scalar_one_or_none()
        before = snapshot(row) if row else None
        work = (await session.execute(select(Preference).where(Preference.user_id == user_id,
            Preference.key == 'work_hours'))).scalar_one_or_none()
        start = (work.value if work else {'start': '09:00'})['start']
        dates = dict(row.value.get('dates', {})) if row else {}
        today = now.date().isoformat()
        dates = {day: hours for day, hours in dates.items() if day >= today}
        ends = change.get('ends', {})
        dates.update({day: {'start': start, 'end': ends.get(day, change['end'])} for day in change['dates']})
        if row is None:
            row = Preference(user_id=user_id, key='work_hours_overrides', value={'dates': dates},
                             source='stated', confidence=1.0, status='active')
            session.add(row)
        else:
            row.value = {'dates': dates}
        await session.flush()
        pending_audits.append((row, before, 'create' if before is None else 'update'))
    elif option_type == 'move_flexible' and 'routine_id' in change:
        routine = (await session.execute(select(Routine).where(Routine.id == UUID(change['routine_id']),
            Routine.user_id == user_id).with_for_update())).scalar_one()
        before = snapshot(routine)
        edits = dict(routine.overrides or {})
        edits[change['original_start']] = {'original_start': change['original_start'], 'start_at': change['start_at'],
                                           'duration_min': change['duration_min'], 'cancelled': False}
        routine.overrides = edits
        pending_audits.append((routine, before, 'update'))
    elif option_type == 'move_flexible':
        task = (await session.execute(select(Task).where(Task.id == UUID(change['task_id']),
            Task.user_id == user_id).with_for_update())).scalar_one()
        before = snapshot(task)
        task.deadline_at = datetime.fromisoformat(change['deadline_at'])
        pending_audits.append((task, before, 'update'))
    before_conflict = snapshot(conflict)
    conflict.status = 'resolved'
    conflict.options = [*conflict.options, {'type': 'applied', 'option': option_type}]
    pending_audits.append((conflict, before_conflict, 'resolve'))
    await session.flush()
    result = await rebuild_plan(session, user_id, now=now)
    for row, before, action in pending_audits:
        (await audit(session, user_id, row, before, action)).batch_id = batch_id
    return {'conflict_id': str(conflict.id), 'status': conflict.status, 'applied': option_type,
            'batch_id': str(batch_id), 'draft_message': option.get('draft_message'),
            'remaining_conflicts': len(result['conflict_rows'])}
