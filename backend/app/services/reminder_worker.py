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
    reminder = (await session.execute(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id).with_for_update())).scalar_one_or_none()
    if reminder is None:
        return None
    if action == 'reschedule':
        from fastapi import HTTPException
        raise HTTPException(status_code=501, detail='Free-slot reschedule suggestions are not implemented')
    if reminder.status in {'acted', 'cancelled'}:
        return reminder
    if action == 'done':
        task = (await session.execute(select(Task).where(Task.id == reminder.item_id,
            Task.user_id == user_id))).scalar_one_or_none()
        if reminder.item_type != 'task' or task is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail='Reminder has no completable task')
        task.status = 'done'
        task.completed_at = datetime.now(timezone.utc)
        await session.execute(update(Reminder).where(Reminder.user_id == user_id,
            Reminder.item_id == task.id, Reminder.status == 'pending', Reminder.id != reminder.id)
            .values(status='cancelled'))
    reminder.action_taken = action
    reminder.status = "acted"
    if action == "snooze_15":
        reminder.fire_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        reminder.status = "pending"
    elif action == "snooze_60":
        reminder.fire_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reminder.status = "pending"
    await session.flush()
    return reminder

