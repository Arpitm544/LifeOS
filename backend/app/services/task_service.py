from __future__ import annotations
from typing import Optional

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActionLog, PlanBlock, Reminder, Task
from ..schemas import TaskCreate
from .domain_service import RULE_KINDS, audit, refresh_blocked, replace_dependencies, snapshot


async def get_task(session: AsyncSession, user_id: UUID, task_id: UUID) -> Optional[Task]:
    return (await session.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id).with_for_update())).scalar_one_or_none()


async def create_task(session: AsyncSession, user_id: UUID, payload: TaskCreate) -> Task:
    from .domain_service import lock_owner
    await lock_owner(session, user_id)
    now = datetime.now(timezone.utc)
    task = Task(user_id=user_id, title=payload.title, notes=payload.notes, deadline_at=payload.deadline_at,
                effort_est_min=payload.effort_est_min, importance=payload.importance,
                category=payload.category.value, recurrence_rrule=payload.recurrence_rrule,
                created_at=now)
    session.add(task)
    await session.flush()
    if payload.depends_on:
        await replace_dependencies(session, user_id, task, payload.depends_on)
    from .planning_service import recalculate_priorities
    await recalculate_priorities(session, user_id, now)
    await audit(session, user_id, task, None, 'create')
    return task


async def latest_action(session: AsyncSession, user_id, entity_id) -> Optional[ActionLog]:
    return (await session.execute(select(ActionLog).where(ActionLog.user_id == user_id,
        ActionLog.entity_id == entity_id).order_by(ActionLog.created_at.desc()).limit(1))).scalar_one_or_none()


async def complete_task_row(session: AsyncSession, user_id, task: Task, actual_effort_min: Optional[int] = None) -> ActionLog:
    before = snapshot(task)
    task.status = 'done'
    task.completed_at = datetime.now(timezone.utc)
    task.effort_actual_min = actual_effort_min
    log = await audit(session, user_id, task, before, 'complete')
    await refresh_blocked(session, user_id)
    return log


async def drop_task(session: AsyncSession, user_id, task: Task) -> UUID:
    """Drop a task and its future planned blocks as one undoable batch."""
    before = snapshot(task)
    task.status = 'dropped'
    batch_id = uuid4()
    blocks = (await session.execute(select(PlanBlock).where(PlanBlock.user_id == user_id,
        PlanBlock.task_id == task.id, PlanBlock.status == 'planned',
        PlanBlock.end_at > datetime.now(timezone.utc)).order_by(PlanBlock.id).with_for_update())).scalars().all()
    for block in blocks:
        block_before = snapshot(block)
        log = await audit(session, user_id, block, block_before, 'delete')
        log.batch_id, log.after = batch_id, None
        await session.delete(block)
    (await audit(session, user_id, task, before, 'delete')).batch_id = batch_id
    await refresh_blocked(session, user_id)
    return batch_id


async def set_custom_reminder(session: AsyncSession, user_id, task: Task, fire_at: datetime) -> Reminder:
    """A user-requested time ("remind me at 6") overrides the rule-based reminders."""
    pending = (Reminder.user_id == user_id, Reminder.item_type == 'task', Reminder.item_id == task.id,
               Reminder.status == 'pending')
    await session.execute(update(Reminder).where(*pending, Reminder.kind.in_(RULE_KINDS + ('custom',)))
                          .values(status='cancelled'))
    reminder = Reminder(user_id=user_id, item_type='task', item_id=task.id, kind='custom',
                        fire_at=fire_at.astimezone(timezone.utc), status='pending',
                        message=f'Reminder: {task.title}.')
    session.add(reminder)
    await session.flush()
    return reminder
