from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import PlanBlock, Reminder, Task
from ..schemas_reminders import ReminderActionRequest
from ..services.planning_service import free_windows, next_free_slots
from ..services.reminder_worker import apply_reminder_action

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class RescheduleRequest(BaseModel):
    start_at: AwareDatetime


def _out(row: Reminder) -> dict:
    return {"id": str(row.id), "item_type": row.item_type, "item_id": str(row.item_id), "kind": row.kind,
            "fire_at": row.fire_at, "status": row.status, "action_taken": row.action_taken,
            "message": row.message, "sent_at": row.sent_at}


@router.get("")
async def list_reminders(limit: int = Query(default=50, ge=1, le=50), session: AsyncSession = Depends(get_session),
                         user_id: UUID = Depends(current_user_id)) -> list[dict]:
    """Notification centre (PRD F3.4): latest reminders that fired or are due."""
    now = datetime.now(timezone.utc)
    rows = (await session.execute(select(Reminder).where(Reminder.user_id == user_id,
        (Reminder.status != 'pending') | (Reminder.fire_at <= now + timedelta(hours=24)),
        Reminder.status != 'cancelled').order_by(Reminder.fire_at.desc()).limit(limit))).scalars().all()
    return [_out(row) for row in rows]


async def _task_for(session, user_id, reminder_id: UUID) -> tuple[Reminder, Task]:
    reminder = (await session.execute(select(Reminder).where(Reminder.id == reminder_id,
        Reminder.user_id == user_id).with_for_update())).scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    task = (await session.execute(select(Task).where(Task.id == reminder.item_id, Task.user_id == user_id))).scalar_one_or_none() \
        if reminder.item_type == 'task' else None
    if task is None or task.status not in {'open', 'blocked'}:
        raise HTTPException(status_code=409, detail='Only reminders for open tasks can be rescheduled')
    return reminder, task


@router.post("/{reminder_id}/action")
async def reminder_action(reminder_id: UUID, request: ReminderActionRequest,
                          session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    if request.action.value == 'reschedule':
        reminder, task = await _task_for(session, user_id, reminder_id)
        slots = await next_free_slots(session, user_id, task_id=task.id, duration_min=min(task.effort_est_min, 90))
        return {"id": str(reminder.id), "status": reminder.status, "action_taken": None,
                "fire_at": reminder.fire_at, "task_id": str(task.id), "slots": slots}
    reminder = await apply_reminder_action(session, user_id=user_id, reminder_id=reminder_id, action=request.action.value)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await session.commit()
    return {"id": str(reminder.id), "status": reminder.status, "action_taken": reminder.action_taken,
            "fire_at": reminder.fire_at}


@router.post("/{reminder_id}/reschedule")
async def reschedule(reminder_id: UUID, request: RescheduleRequest, session: AsyncSession = Depends(get_session),
                     user_id: UUID = Depends(current_user_id)) -> dict:
    """Move the task's next plan block (and this reminder) to a chosen free slot."""
    from ..services.domain_service import lock_owner, audit, snapshot
    await lock_owner(session, user_id)
    reminder, task = await _task_for(session, user_id, reminder_id)
    duration = min(task.effort_est_min, 90)
    start = request.start_at.astimezone(timezone.utc)
    windows = await free_windows(session, user_id, task_id=task.id)
    if not any(window.start <= start and start + timedelta(minutes=duration) <= window.end for window in windows):
        raise HTTPException(status_code=409, detail='That time is no longer free')
    now = datetime.now(timezone.utc)
    block = (await session.execute(select(PlanBlock).where(PlanBlock.user_id == user_id, PlanBlock.task_id == task.id,
        PlanBlock.status == 'planned', PlanBlock.end_at > now).order_by(PlanBlock.start_at).limit(1)
        .with_for_update())).scalar_one_or_none()
    if block is None:
        block = PlanBlock(user_id=user_id, task_id=task.id, start_at=start, end_at=start + timedelta(minutes=duration),
                          status='planned', plan_date=start.replace(hour=0, minute=0, second=0, microsecond=0))
        session.add(block)
        await session.flush()
        log = await audit(session, user_id, block, None, 'create')
    else:
        before = snapshot(block)
        length = block.end_at - block.start_at
        block.start_at, block.end_at = start, start + length
        log = await audit(session, user_id, block, before, 'update')
    reminder.fire_at, reminder.status, reminder.action_taken = start, 'pending', 'reschedule'
    await session.commit()
    return {"id": str(reminder.id), "status": reminder.status, "fire_at": reminder.fire_at,
            "plan_block": {"id": str(block.id), "start_at": block.start_at, "end_at": block.end_at},
            "action_id": str(log.id)}

