from fastapi import APIRouter, Depends
from ..auth import current_user_id

from ..schemas_reminders import ReminderPreviewRequest
from ..services.reminder_service import task_reminder_times

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.post("/preview")
async def preview(request: ReminderPreviewRequest, user_id = Depends(current_user_id)) -> dict:
    return {"reminders": [{"kind": kind, "fire_at": fire_at} for kind, fire_at in task_reminder_times(deadline=request.deadline, effort_min=request.effort_min, now=request.now)]}

