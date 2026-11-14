"""Shared transaction helpers. Callers own commit/rollback boundaries."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import DateTime, select, delete, update

from ..models import ActionLog, ActivityEvent, Event, PlanBlock, Reminder, Task, TaskDependency, Preference, Routine


def snapshot(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        result[column.name] = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, UUID) else value
    return result


async def audit(session, owner, row, before, action_type):
    await session.flush()
    # Assign the identifier here (rather than waiting for INSERT) so the activity
    # record always points at its audit record on every supported database.
    log = ActionLog(id=uuid4(), user_id=owner, action_type=action_type, entity=row.__tablename__,
        entity_id=row.id, before=before, after=snapshot(row))
    session.add(log)
    session.add(ActivityEvent(user_id=owner, type=(row.__tablename__ + '_' + action_type)[:32],
        entity_id=row.id, payload={'action_id': str(log.id)}))
    if isinstance(row, (Task, Event)):
        await sync_reminders(session, owner, row)
    elif isinstance(row, Preference):
        await sync_all_reminders(session, owner)
    await session.flush()
    return log


async def sync_all_reminders(session, owner):
    for model in (Task, Event):
        rows = (await session.execute(select(model).where(model.user_id == owner))).scalars().all()
        for row in rows:
            await sync_reminders(session, owner, row)


async def sync_reminders(session, owner, row):
    from .reminder_service import task_reminder_times, event_reminder_time, move_out_of_quiet_hours
    from zoneinfo import ZoneInfo
    kind = 'task' if isinstance(row, Task) else 'event'
    await session.execute(update(Reminder).where(Reminder.user_id == owner, Reminder.item_type == kind,
        Reminder.item_id == row.id, Reminder.status == 'pending').values(status='cancelled'))
    if (kind == 'task' and row.status not in {'open', 'blocked'}) or (kind == 'event' and row.cancelled):
        return
    prefs = (await session.execute(select(Preference).where(Preference.user_id == owner,
        Preference.status == 'active'))).scalars().all()
    values = {item.key: item.value for item in prefs}
    tz = ZoneInfo(values.get('timezone', {}).get('name', 'UTC'))
    quiet = values.get('quiet_hours', {'start': '22:30', 'end': '07:30'})
    now = datetime.now(timezone.utc)
    deadline = row.deadline_at if kind == 'task' else row.start_at
    if deadline is None:
        return
    deadline = deadline.replace(tzinfo=timezone.utc) if deadline.tzinfo is None else deadline
    times = task_reminder_times(deadline=deadline, effort_min=row.effort_est_min, now=now) if kind == 'task' else [('event', event_reminder_time(start=deadline, location=row.location))]
    scheduled = set()
    for reminder_kind, fire_at in times:
        fire_at = move_out_of_quiet_hours(fire_at.astimezone(tz),
            quiet_start=tuple(map(int, quiet['start'].split(':'))),
            quiet_end=tuple(map(int, quiet['end'].split(':'))), deadline=deadline.astimezone(tz))
        if fire_at < now or fire_at in scheduled:
            continue
        scheduled.add(fire_at)
        session.add(Reminder(user_id=owner, item_type=kind, item_id=row.id, kind=reminder_kind,
            fire_at=fire_at.astimezone(timezone.utc), status='pending', message=row.title))


async def lock_owner(session, owner):
    if session.get_bind().dialect.name == 'postgresql':
        from sqlalchemy import text
        await session.execute(text('SELECT pg_advisory_xact_lock(7301, hashtext(:owner))'),
                              {'owner': str(owner)})


async def lock_tasks(session, owner, ids=None):
    await lock_owner(session, owner)
    query = select(Task).where(Task.user_id == owner)
    if ids is not None:
        query = query.where(Task.id.in_(ids))
    return list((await session.execute(query.order_by(Task.id).with_for_update())).scalars())


def assert_acyclic(edges):
    graph = {}
    for task, dependency in edges:
        graph.setdefault(task, []).append(dependency)
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            raise HTTPException(status_code=409, detail='Circular task dependency')
        if node in done:
            return
        visiting.add(node)
        for child in graph.get(node, []):
            visit(child)
        visiting.remove(node)
        done.add(node)
    for node in graph:
        visit(node)


async def replace_dependencies(session, owner, task, dependencies):
    tasks = await lock_tasks(session, owner)
    owned = {item.id for item in tasks}
    if any(identity not in owned for identity in dependencies):
        raise HTTPException(status_code=404, detail='Dependency task not found')
    rows = (await session.execute(select(TaskDependency).where(TaskDependency.user_id == owner))).scalars().all()
    edges = [(row.task_id, row.depends_on_task_id) for row in rows if row.task_id != task.id]
    edges += [(task.id, identity) for identity in set(dependencies)]
    assert_acyclic(edges)
    await session.execute(delete(TaskDependency).where(TaskDependency.user_id == owner, TaskDependency.task_id == task.id))
    session.add_all([TaskDependency(user_id=owner, task_id=task.id, depends_on_task_id=identity) for identity in set(dependencies)])
    await session.flush()
    await refresh_blocked(session, owner)


async def refresh_blocked(session, owner):
    tasks = list((await session.execute(select(Task).where(Task.user_id == owner))).scalars())
    statuses = {task.id: task.status for task in tasks}
    edges = (await session.execute(select(TaskDependency).where(TaskDependency.user_id == owner))).scalars().all()
    blocked = {edge.task_id for edge in edges if statuses.get(edge.depends_on_task_id) != 'done'}
    for task in tasks:
        if task.status in {'open', 'blocked'}:
            task.status = 'blocked' if task.id in blocked else 'open'


async def undo_logged_action(session, owner, action_id):
    await lock_owner(session, owner)
    log = (await session.execute(select(ActionLog).where(ActionLog.id == action_id,
        ActionLog.user_id == owner).with_for_update())).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail='Action not found')
    if log.undone_at:
        raise HTTPException(status_code=409, detail='Action already undone')
    if datetime.now(timezone.utc) > log.created_at.replace(tzinfo=timezone.utc) + timedelta(seconds=10):
        raise HTTPException(status_code=409, detail='Undo expired')
    if log.entity == 'task_dependencies':
        tasks = {task.id: task for task in await lock_tasks(session, owner)}
        current = list((await session.execute(select(TaskDependency.depends_on_task_id).where(
            TaskDependency.user_id == owner, TaskDependency.task_id == log.entity_id))).scalars())
        if log.entity_id not in tasks or sorted(map(str,current)) != log.after['depends_on']:
            raise HTTPException(status_code=409, detail='Dependencies changed since action')
        await replace_dependencies(session, owner, tasks[log.entity_id], [UUID(item) for item in log.before['depends_on']])
        log.undone_at = datetime.now(timezone.utc)
        await session.flush()
        return True
    model = {'task': Task, 'tasks': Task, 'events': Event, 'preferences': Preference, 'routines': Routine, 'plan_blocks': PlanBlock}.get(log.entity)
    if model is None:
        raise HTTPException(status_code=409, detail='This action cannot be undone')
    row = (await session.execute(select(model).where(model.id == log.entity_id,
        model.user_id == owner).with_for_update())).scalar_one_or_none()
    if log.after is None and log.action_type == 'delete' and row is None:
        values = dict(log.before)
        for column in model.__table__.columns:
            value = values.get(column.name)
            if value is not None and isinstance(column.type, DateTime):
                values[column.name] = datetime.fromisoformat(value)
            elif value is not None and str(column.type) == 'UUID':
                values[column.name] = UUID(value)
        if model is PlanBlock:
            start, end = values['start_at'], values['end_at']
            overlap = select(PlanBlock.id).where(PlanBlock.user_id == owner,
                PlanBlock.status == 'planned', PlanBlock.start_at < end, PlanBlock.end_at > start)
            if (await session.execute(overlap)).first():
                raise HTTPException(status_code=409, detail='Restored block would overlap planned work')
        session.add(model(**values))
        log.undone_at = datetime.now(timezone.utc)
        await session.flush()
        if model is Preference:
            await sync_all_reminders(session, owner)
        return True
    if row is None or snapshot(row) != log.after:
        raise HTTPException(status_code=409, detail='Item changed since this action')
    if log.action_type == 'create':
        # Refuse cascading destruction of later work.
        if model is Task:
            if (await session.execute(select(PlanBlock.id).where(PlanBlock.user_id == owner, PlanBlock.task_id == row.id))).first():
                raise HTTPException(status_code=409, detail='Task has scheduled work; undo refused')
            if (await session.execute(select(TaskDependency.task_id).where(TaskDependency.user_id == owner,
                TaskDependency.depends_on_task_id == row.id))).first():
                raise HTTPException(status_code=409, detail='Another task depends on this item')
            await session.execute(delete(Reminder).where(Reminder.user_id == owner,
                Reminder.item_type == 'task', Reminder.item_id == row.id))
        await session.delete(row)
    else:
        for column in model.__table__.columns:
            if column.name in {'id','user_id'}:
                continue
            value = log.before[column.name]
            if value is not None and isinstance(column.type, DateTime):
                value = datetime.fromisoformat(value)
            setattr(row, column.name, value)
    log.undone_at = datetime.now(timezone.utc)
    await session.flush()
    if model is Task:
        await refresh_blocked(session, owner)
    if log.action_type != 'create' and model in (Task, Event):
        await sync_reminders(session, owner, row)
    if model is Preference:
        await sync_all_reminders(session, owner)
    return True
