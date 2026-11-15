from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
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


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _task_for(session, user_id, reminder_id: UUID, *, lock: bool = True) -> tuple[Reminder, Task]:
    query = select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    reminder = (await session.execute(query.with_for_update() if lock else query)).scalar_one_or_none()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.status == 'cancelled':
        raise HTTPException(status_code=409, detail='This reminder was cancelled')
    task = (await session.execute(select(Task).where(Task.id == reminder.item_id, Task.user_id == user_id))).scalar_one_or_none()         if reminder.item_type == 'task' else None
    # Blocked tasks are never planned, so they cannot be rescheduled into a block.
    if task is None or task.status != 'open':
        raise HTTPException(status_code=409, detail='Only reminders for open tasks can be rescheduled')
    return reminder, task


async def _next_block(session, user_id, task_id, *, lock: bool = True) -> PlanBlock | None:
    query = select(PlanBlock).where(PlanBlock.user_id == user_id, PlanBlock.task_id == task_id,
        PlanBlock.status == 'planned', PlanBlock.end_at > datetime.now(timezone.utc)).order_by(PlanBlock.start_at).limit(1)
    return (await session.execute(query.with_for_update() if lock else query)).scalar_one_or_none()


def _block_minutes(task: Task, block: PlanBlock | None) -> int:
    if block is not None:
        return int((_utc(block.end_at) - _utc(block.start_at)).total_seconds() // 60)
    return min(task.effort_est_min, 90)


@router.post("/{reminder_id}/action")
async def reminder_action(reminder_id: UUID, request: ReminderActionRequest,
                          session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    if request.action.value == 'reschedule':
        reminder, task = await _task_for(session, user_id, reminder_id, lock=False)
        minutes = _block_minutes(task, await _next_block(session, user_id, task.id, lock=False))
        slots = await next_free_slots(session, user_id, task_id=task.id, duration_min=minutes,
                                      deadline=task.deadline_at)
        # Offering slots writes nothing; the request session closes without commit.
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
    """Move the task's next plan block (and its reminders) to a chosen free slot."""
    from ..services.domain_service import lock_owner, audit, snapshot
    from ..services.planning_service import active_preferences, planning_profile
    await lock_owner(session, user_id)
    reminder, task = await _task_for(session, user_id, reminder_id)
    block = await _next_block(session, user_id, task.id)
    minutes = _block_minutes(task, block)
    start = request.start_at.astimezone(timezone.utc)
    end = start + timedelta(minutes=minutes)
    if task.deadline_at is not None and end > _utc(task.deadline_at):
        raise HTTPException(status_code=409, detail='That slot ends after the deadline')
    windows = await free_windows(session, user_id, task_id=task.id)
    if not any(window.start <= start and end <= window.end for window in windows):
        raise HTTPException(status_code=409, detail='That time is no longer free')
    zone, _ = planning_profile(await active_preferences(session, user_id))
    plan_date = start.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    old_start = _utc(block.start_at) if block is not None else None
    if block is None:
        block = PlanBlock(user_id=user_id, task_id=task.id, start_at=start, end_at=end,
                          status='planned', plan_date=plan_date)
        session.add(block)
        await session.flush()
        log = await audit(session, user_id, block, None, 'create')
    else:
        before = snapshot(block)
        block.start_at, block.end_at, block.plan_date = start, end, plan_date
        log = await audit(session, user_id, block, before, 'update')
    def remember(item):
        return {'id': str(item.id), 'fire_at': _utc(item.fire_at).isoformat(), 'status': item.status,
                'action_taken': item.action_taken}
    restore = [remember(reminder)]
    # The moved block's own start reminder follows it.
    if old_start is not None:
        moved = (await session.execute(select(Reminder).where(Reminder.user_id == user_id,
            Reminder.item_type == 'task', Reminder.item_id == task.id, Reminder.kind == 'plan_block',
            Reminder.status == 'pending', Reminder.id != reminder.id))).scalars().all()
        for item in moved:
            if _utc(item.fire_at) == old_start:
                restore.append(remember(item))
                item.fire_at = start
    reminder.fire_at, reminder.status, reminder.action_taken = start, 'pending', 'reschedule'
    # Undo of this action restores the reminders too (metadata, ignored by the snapshot check).
    log.after = {**log.after, '_reminder_restore': restore}
    await session.commit()
    return {"id": str(reminder.id), "status": reminder.status, "fire_at": reminder.fire_at,
            "plan_block": {"id": str(block.id), "start_at": block.start_at, "end_at": block.end_at},
            "action_id": str(log.id)}


push_router = APIRouter(prefix="/api/push-actions", tags=["reminders"])


class PushActionRequest(BaseModel):
    action: str


@push_router.post("/{reminder_id}")
async def push_action(reminder_id: UUID, request: PushActionRequest,
                      x_push_token: str | None = Header(default=None)) -> dict:
    """Done / Snooze tapped on a push notification (PRD F3.2).

    The service worker has no Clerk session, so it sends the signed token from the
    push payload instead. The token is bound to this reminder and its owner.
    """
    from ..config import get_settings
    from ..db import user_session
    from ..services.push_tokens import ALLOWED_ACTIONS, verify_action_token
    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail="Unsupported notification action")
    user_id = verify_action_token(get_settings(), x_push_token or '', reminder_id=str(reminder_id))
    if user_id is None:
        raise HTTPException(status_code=401, detail="Notification action expired; open LifeOS to continue")
    async with user_session(user_id) as session:
        reminder = await apply_reminder_action(session, user_id=user_id, reminder_id=reminder_id, action=request.action)
        if reminder is None:
            raise HTTPException(status_code=404, detail="Reminder not found")
        await session.commit()
        return {"id": str(reminder.id), "status": reminder.status, "action_taken": reminder.action_taken,
                "fire_at": reminder.fire_at}
