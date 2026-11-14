"""Data export and account deletion (PRD 9, data protection)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import (ActionLog, ActivityEvent, Conflict, Event, IdempotencyRecord, Message, PlanBlock, Preference,
                      PushSubscription, Reminder, Routine, Suggestion, Task, TaskDependency, User)
from ..services.domain_service import snapshot

router = APIRouter(prefix="/api", tags=["account"])

# Children before parents so deletes never trip a foreign key.
OWNED = [('reminders', Reminder), ('plan_blocks', PlanBlock), ('task_dependencies', TaskDependency),
         ('conflicts', Conflict), ('suggestions', Suggestion), ('action_log', ActionLog),
         ('activity_events', ActivityEvent), ('messages', Message), ('idempotency_records', IdempotencyRecord),
         ('push_subscriptions', PushSubscription), ('preferences', Preference), ('routines', Routine),
         ('events', Event), ('tasks', Task)]
SECRET_COLUMNS = {'push_subscriptions': {'p256dh', 'auth'}, 'idempotency_records': {'response'}}


@router.get("/export")
async def export_data(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    data = {'exported_at': datetime.now(timezone.utc).isoformat(), 'user_id': str(user_id)}
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    data['user'] = snapshot(user) if user else None
    for name, model in OWNED:
        rows = (await session.execute(select(model).where(model.user_id == user_id))).scalars().all()
        hidden = SECRET_COLUMNS.get(name, set())
        data[name] = [{key: value for key, value in snapshot(row).items() if key not in hidden} for row in rows]
    return data


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(confirmed: bool = False, session: AsyncSession = Depends(get_session),
                         user_id: UUID = Depends(current_user_id)) -> None:
    """Remove every LifeOS row for this user, including push subscriptions.

    The Clerk identity itself is deleted through Clerk by the frontend.
    """
    if not confirmed:
        raise HTTPException(status_code=409, detail='Explicit confirmation required: confirmed=true')
    for _, model in OWNED:
        await session.execute(delete(model).where(model.user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))
    await session.commit()
