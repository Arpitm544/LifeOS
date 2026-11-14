from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..schemas_capacity import CapacityCheckRequest
from ..services.capacity_guard import CapacityTask, check_capacity

router = APIRouter(prefix="/api/capacity", tags=["capacity"])


@router.post("/check")
async def capacity_check(request: CapacityCheckRequest, session: AsyncSession = Depends(get_session),
                         user_id=Depends(current_user_id)) -> dict:
    """With `hypothetical`, check new work against the user's saved calendar (no write).

    Without it, run the pure Capacity Guard formula on the supplied numbers.
    """
    if request.hypothetical is not None:
        from ..services.chat_orchestrator import hypothetical_capacity
        item = request.hypothetical
        now = datetime.now(timezone.utc)
        if item.deadline <= now:
            raise HTTPException(status_code=422, detail='Deadline must be in the future')
        result = await hypothetical_capacity(session, user_id, title=item.title, effort_min=item.effort_min,
                                             deadline=item.deadline, now=now, category=item.category)
        await session.rollback()
        return result
    conflicts = check_capacity(
        tasks=[CapacityTask(item.id, item.title, item.effort_min, item.deadline, item.priority_score, item.flexible) for item in request.tasks],
        free_minutes_until=request.free_minutes_until,
    )
    return {"fits": not conflicts, "conflicts": [{"deadline": item.deadline, "needed_min": item.needed_min,
             "free_min": item.free_min, "shortfall_min": item.shortfall_min, "task_ids": item.task_ids,
             "options": item.options} for item in conflicts]}
