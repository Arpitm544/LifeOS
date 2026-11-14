from __future__ import annotations
from typing import Optional

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Task
from ..schemas import TaskCreate
from .domain_service import audit, replace_dependencies


async def get_task(session: AsyncSession, user_id: UUID, task_id: UUID) -> Optional[Task]:
    return (await session.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id).with_for_update())).scalar_one_or_none()


async def create_task(session: AsyncSession, user_id: UUID, payload: TaskCreate) -> Task:
    from .domain_service import lock_owner
    await lock_owner(session, user_id)
    now = datetime.now(timezone.utc)
    task = Task(user_id=user_id, title=payload.title, deadline_at=payload.deadline_at,
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

