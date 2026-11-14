from fastapi import APIRouter, Depends
from ..auth import current_user_id

from ..schemas_capacity import CapacityCheckRequest
from ..services.capacity_guard import CapacityTask, check_capacity

router = APIRouter(prefix="/api/capacity", tags=["capacity"])


@router.post("/check")
async def capacity_check(request: CapacityCheckRequest, user_id = Depends(current_user_id)) -> dict:
    conflicts = check_capacity(
        tasks=[CapacityTask(item.id, item.title, item.effort_min, item.deadline, item.priority_score, item.flexible) for item in request.tasks],
        free_minutes_until=request.free_minutes_until,
    )
    return {"fits": not conflicts, "conflicts": [{"deadline": item.deadline, "needed_min": item.needed_min,
             "free_min": item.free_min, "shortfall_min": item.shortfall_min, "task_ids": item.task_ids,
             "options": item.options} for item in conflicts]}

