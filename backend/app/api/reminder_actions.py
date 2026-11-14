from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..schemas_reminders import ReminderActionRequest
from ..services.reminder_worker import apply_reminder_action

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.post("/{reminder_id}/action")
async def reminder_action(reminder_id: UUID, request: ReminderActionRequest,
                          session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    reminder = await apply_reminder_action(session, user_id=user_id, reminder_id=reminder_id, action=request.action.value)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await session.commit()
    return {"id": str(reminder.id), "status": reminder.status, "action_taken": reminder.action_taken,
            "fire_at": reminder.fire_at}

