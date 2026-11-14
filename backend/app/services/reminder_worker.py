from __future__ import annotations
from typing import Optional


from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Reminder, Task


async def claim_due_reminders(session: AsyncSession, *, batch_size: int = 100) -> list[Reminder]:
    now = datetime.now(timezone.utc)
    reminders = list((await session.execute(
        select(Reminder).where(Reminder.status == "pending", Reminder.fire_at <= now)
        .order_by(Reminder.fire_at).limit(batch_size).with_for_update(skip_locked=True)
    )).scalars().all())
    # Caller must deliver while holding this transaction, then mark sent.
    # Selecting/locking alone is not proof of delivery.
    return reminders


async def apply_reminder_action(session: AsyncSession, *, user_id: UUID, reminder_id: UUID, action: str) -> Optional[Reminder]:
    from .domain_service import lock_owner, snapshot, audit, refresh_blocked
    await lock_owner(session, user_id)
    reminder = (await session.execute(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id).with_for_update())).scalar_one_or_none()
    if reminder is None:
        return None
    if action == 'reschedule':
        # Slots are offered by the API layer (next_free_slots); nothing changes here.
        return reminder
    if reminder.status in {'acted', 'cancelled'}:
        return reminder
    if action == 'done':
        task = (await session.execute(select(Task).where(Task.id == reminder.item_id,
            Task.user_id == user_id))).scalar_one_or_none()
        if reminder.item_type != 'task' or task is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail='Reminder has no completable task')
        before = snapshot(task)
        task.status = 'done'
        task.completed_at = datetime.now(timezone.utc)
        await audit(session, user_id, task, before, 'complete')
        await refresh_blocked(session, user_id)
        await session.execute(update(Reminder).where(Reminder.user_id == user_id,
            Reminder.item_id == task.id, Reminder.status == 'pending', Reminder.id != reminder.id)
            .values(status='cancelled'))
    reminder.action_taken = action
    reminder.status = "acted"
    from ..models import ActivityEvent
    category = None
    if reminder.item_type == 'task':
        category = (await session.execute(select(Task.category).where(Task.id == reminder.item_id,
            Task.user_id == user_id))).scalar_one_or_none()
    session.add(ActivityEvent(user_id=user_id, type='reminder_snoozed' if action.startswith('snooze') else 'reminder_' + action,
        entity_id=reminder.id, payload={'kind': reminder.kind, 'category': category or 'other', 'action': action}))
    if action == "snooze_15":
        reminder.fire_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        reminder.status = "pending"
    elif action == "snooze_60":
        reminder.fire_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reminder.status = "pending"
    await session.flush()
    return reminder

