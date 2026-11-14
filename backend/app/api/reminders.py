from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..schemas_reminders import ReminderPreviewRequest
from ..services.planning_service import active_preferences
from ..services.reminder_service import task_reminder_times

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.post("/preview")
async def preview(request: ReminderPreviewRequest, session: AsyncSession = Depends(get_session),
                  user_id=Depends(current_user_id)) -> dict:
    # Same lead time the real reminders use (reminder_lead preference, default 60 min).
    lead = int((await active_preferences(session, user_id)).get('reminder_lead', {}).get('minutes', 60))
    return {"reminders": [{"kind": kind, "fire_at": fire_at} for kind, fire_at in task_reminder_times(
        deadline=request.deadline, effort_min=request.effort_min, now=request.now, buffer_min=lead)],
        "lead_min": lead}
