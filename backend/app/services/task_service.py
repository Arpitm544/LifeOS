from __future__ import annotations
from typing import Optional

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Task
from ..schemas import TaskCreate
from .priority_engine import calculate_priority
from .domain_service import audit, replace_dependencies


async def get_task(session: AsyncSession, user_id: UUID, task_id: UUID) -> Optional[Task]:
    return (await session.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id).with_for_update())).scalar_one_or_none()


async def create_task(session: AsyncSession, user_id: UUID, payload: TaskCreate) -> Task:
    now = datetime.now(timezone.utc)
    task = Task(user_id=user_id, title=payload.title, deadline_at=payload.deadline_at,
                effort_est_min=payload.effort_est_min, importance=payload.importance,
                category=payload.category.value, recurrence_rrule=payload.recurrence_rrule,
                created_at=now)
    result = calculate_priority(now=now, deadline=task.deadline_at, effort_min=task.effort_est_min,
                                importance=task.importance, blocking_count=0,
                                created_at=now, free_working_hours=40)
    task.priority_score, task.priority_band = result.score, result.band
    session.add(task)
    await session.flush()
    if payload.depends_on:
        await replace_dependencies(session, user_id, task, payload.depends_on)
    await audit(session, user_id, task, None, 'create')
    return task

