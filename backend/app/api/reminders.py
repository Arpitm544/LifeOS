from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..schemas_reminders import ReminderPreviewRequest
from ..services.domain_service import scheduled_times
from ..services.planning_service import active_preferences

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.post("/preview")
async def preview(request: ReminderPreviewRequest, session: AsyncSession = Depends(get_session),
                  user_id=Depends(current_user_id)) -> dict:
    """The task reminders that would be scheduled: same lead, quiet hours and past-time rules."""
    values = await active_preferences(session, user_id)
    times = scheduled_times(values, deadline=request.deadline, now=request.now, effort_min=request.effort_min)
    return {"reminders": [{"kind": kind, "fire_at": fire_at} for kind, fire_at in times],
            "lead_min": int(values.get('reminder_lead', {}).get('minutes', 60))}
