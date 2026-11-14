from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_session
from ..auth import current_user_id

from ..schemas_plan import PlanGenerateRequest
from ..services.scheduler import BusyBlock, SchedulableTask, build_free_slots, generate_plan
from ..services.planning_service import rebuild_plan

router = APIRouter(prefix="/api/plan", tags=["planning"])


@router.post("/generate")
async def generate(request: PlanGenerateRequest, user_id = Depends(current_user_id)) -> dict:
    slots = build_free_slots(window_start=request.window_start, window_end=request.window_end,
                             working_hours=request.working_hours,
                             busy=[BusyBlock(item.start, item.end) for item in request.busy])
    blocks, unplaced = generate_plan(
        tasks=[SchedulableTask(item.id, item.effort_min, item.deadline, item.priority_score, item.blocked) for item in request.tasks],
        slots=slots,
    )
    return {"blocks": [{"task_id": block.task_id, "start": block.start, "end": block.end} for block in blocks],
            "unplaced_task_ids": [item.id for item in unplaced],
            "free_slots": [{"start": slot.start, "end": slot.end} for slot in slots]}


@router.post('/rebuild')
async def rebuild(days: int = Query(default=7, ge=1, le=14), session: AsyncSession = Depends(get_session),
                  user_id=Depends(current_user_id)) -> dict:
    try:
        result = await rebuild_plan(session, user_id, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return {'timezone': result['timezone'],
        'blocks': [{'task_id': str(block.task_id), 'start_at': block.start_at, 'end_at': block.end_at}
                   for block in result['blocks']],
        'unplaced_task_ids': result['unplaced_task_ids'],
        'conflicts': [{'deadline': row.deadline, 'shortfall_min': row.shortfall_min,
                       'task_ids': row.task_ids, 'options': row.options} for row in result['conflicts']]}

