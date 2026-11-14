from __future__ import annotations
from typing import Optional

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import ActionLog, Task, TaskDependency
from ..schemas import TaskCreate, TaskRead, TaskPatch
from ..services.task_service import complete_task_row, create_task, drop_task, get_task
from ..services.domain_service import audit, snapshot, refresh_blocked, lock_tasks, replace_dependencies
from pydantic import BaseModel, Field

from ..services.planning_service import detect_conflicts, recalculate_priorities

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class DependenciesUpdate(BaseModel):
    depends_on: list[UUID] = Field(max_length=100)


@router.put('/{task_id}/dependencies', response_model=TaskRead)
async def set_dependencies(task_id: UUID, payload: DependenciesUpdate,
    session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    await lock_tasks(session, user_id)
    task = await get_task(session, user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    prior = list((await session.execute(select(TaskDependency.depends_on_task_id).where(
        TaskDependency.user_id == user_id, TaskDependency.task_id == task_id))).scalars())
    await replace_dependencies(session, user_id, task, payload.depends_on)
    await recalculate_priorities(session, user_id)
    session.add(ActionLog(user_id=user_id, entity='task_dependencies', entity_id=task_id,
        action_type='update', before={'depends_on': sorted(map(str,prior))},
        after={'depends_on': sorted(map(str,set(payload.depends_on)))}))
    await session.commit()
    await session.refresh(task)
    return task


@router.patch('/{task_id}', response_model=TaskRead)
async def edit_task(task_id: UUID, payload: TaskPatch, session: AsyncSession = Depends(get_session),
                    user_id: UUID = Depends(current_user_id)):
    await lock_tasks(session, user_id)
    task = (await session.execute(select(Task).where(Task.id == task_id,
        Task.user_id == user_id).with_for_update())).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    changes = payload.model_dump(exclude_unset=True, mode='json')
    if not changes:
        return task
    before = snapshot(task)
    for key in changes:
        setattr(task, key, getattr(payload, key))
    if changes.keys() & {'deadline_at', 'effort_est_min', 'importance', 'pinned', 'category'}:
        await recalculate_priorities(session, user_id)
    await audit(session, user_id, task, before, 'update')
    if changes.keys() & {'deadline_at', 'effort_est_min', 'pinned', 'category'}:
        await detect_conflicts(session, user_id)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    band: Optional[str] = Query(default=None, pattern='^P[123]$'),
    due_before: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(current_user_id),
) -> list[Task]:
    query = select(Task).where(Task.user_id == user_id).order_by(Task.pinned.desc(), Task.priority_score.desc(), Task.deadline_at)
    if band:
        query = query.where(Task.priority_band == band)
    if due_before:
        if due_before.tzinfo is None:
            raise HTTPException(status_code=422, detail='due_before requires a timezone')
        query = query.where(Task.deadline_at <= due_before)
    if status_filter:
        query = query.where(Task.status == status_filter)
    return list((await session.execute(query)).scalars().all())


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def add_task(payload: TaskCreate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> Task:
    task = await create_task(session, user_id, payload)
    await detect_conflicts(session, user_id)
    await session.commit()
    await session.refresh(task)
    return task


@router.post("/{task_id}/complete", response_model=TaskRead)
async def complete_task(task_id: UUID, actual_effort_min: Optional[int] = Query(default=None, ge=0, le=10080),
                        session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> Task:
    await lock_tasks(session, user_id)
    task = await get_task(session, user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in {'done', 'dropped'}:
        raise HTTPException(status_code=409, detail=f'Task is already {task.status}')
    await complete_task_row(session, user_id, task, actual_effort_min)
    await detect_conflicts(session, user_id)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: UUID, confirmed: bool = False, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> None:
    if not confirmed:
        raise HTTPException(status_code=409, detail='Explicit confirmation required: confirmed=true')
    await lock_tasks(session, user_id)
    task = await get_task(session, user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await drop_task(session, user_id, task)
    await session.commit()



class ActualEffort(BaseModel):
    """One-tap answer to "How long did it take?" (PRD 5.5 step 4)."""
    answer: str = Field(pattern='^(less|about_right|more|custom)$')
    minutes: Optional[int] = Field(default=None, ge=1, le=1440)


@router.post('/{task_id}/actual-effort', response_model=TaskRead)
async def record_actual_effort(task_id: UUID, payload: ActualEffort, session: AsyncSession = Depends(get_session),
                               user_id: UUID = Depends(current_user_id)) -> Task:
    task = await get_task(session, user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    if task.status != 'done':
        raise HTTPException(status_code=409, detail='Record effort after completing the task')
    if payload.answer == 'custom' and payload.minutes is None:
        raise HTTPException(status_code=422, detail='minutes is required for a custom answer')
    factor = {'less': 0.75, 'about_right': 1.0, 'more': 1.5}.get(payload.answer)
    before = snapshot(task)
    task.effort_actual_min = payload.minutes if factor is None else round(task.effort_est_min * factor)
    await audit(session, user_id, task, before, 'effort')
    await session.commit()
    await session.refresh(task)
    return task
