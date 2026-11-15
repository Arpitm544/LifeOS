from __future__ import annotations
from typing import Optional


from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import Event, PlanBlock, Task
from ..schemas_plan_blocks import PlanBlockCreate, PlanBlockPatch

from ..services.domain_service import lock_owner
from ..services.planning_service import active_preferences, planning_profile


async def local_plan_date(session, owner, start):
    zone, _ = planning_profile(await active_preferences(session, owner))
    return start.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


router = APIRouter(prefix="/api/plan-blocks", tags=["planning"])


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def record_block_move(session, owner, block: PlanBlock) -> None:
    """Log the local hour a block was moved to (F6 rule input), then re-run the inference rules."""
    from ..models import ActivityEvent
    from ..services.preference_inference import local_hour, run_inference
    session.add(ActivityEvent(user_id=owner, type='block_moved', entity_id=block.id,
        occurred_at=datetime.now(timezone.utc),
        payload={'hour': local_hour(block.start_at, await active_preferences(session, owner))}))
    await session.flush()
    await run_inference(session, owner)


def output(block: PlanBlock) -> dict:
    return {"id": str(block.id), "task_id": str(block.task_id), "start_at": block.start_at,
            "end_at": block.end_at, "status": block.status, "plan_date": block.plan_date}


@router.get("")
async def list_blocks(plan_date: Optional[datetime] = None, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> list[dict]:
    query = select(PlanBlock).where(PlanBlock.user_id == user_id).order_by(PlanBlock.start_at)
    if plan_date:
        query = query.where(PlanBlock.plan_date == plan_date)
    return [output(block) for block in (await session.execute(query)).scalars().all()]


async def validate_placement(session, user_id, task_id, start, end, exclude_id=None):
    await lock_owner(session, user_id)
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise HTTPException(status_code=422, detail="Use timezone-aware start/end with end after start")
    task = (await session.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id)
                                  .with_for_update())).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "open":
        raise HTTPException(status_code=409, detail="Task cannot be scheduled in its current status")
    if task.deadline_at and end > task.deadline_at.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=409, detail="Block exceeds task deadline")
    query = select(PlanBlock.id).where(PlanBlock.user_id == user_id, PlanBlock.status == "planned",
                                       PlanBlock.start_at < end, PlanBlock.end_at > start)
    if exclude_id:
        query = query.where(PlanBlock.id != exclude_id)
    if (await session.execute(query)).first():
        raise HTTPException(status_code=409, detail="Block overlaps another planned block")
    from datetime import timedelta
    event = select(Event.id).where(Event.user_id == user_id, Event.cancelled == False,
        Event.start_at < end + timedelta(minutes=10), Event.end_at > start - timedelta(minutes=10))
    if (await session.execute(event)).first():
        raise HTTPException(status_code=409, detail="Block overlaps an event buffer")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_block(payload: PlanBlockCreate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    await validate_placement(session, user_id, payload.task_id, payload.start_at, payload.end_at)
    block = PlanBlock(user_id=user_id, task_id=payload.task_id, start_at=payload.start_at,
                      end_at=payload.end_at, plan_date=await local_plan_date(session, user_id, payload.start_at))
    session.add(block)
    await session.commit()
    await session.refresh(block)
    return output(block)


@router.patch("/{block_id}")
async def patch_block(block_id: UUID, payload: PlanBlockPatch, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    await lock_owner(session, user_id)
    block = (await session.execute(select(PlanBlock).where(PlanBlock.id == block_id, PlanBlock.user_id == user_id))).scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=404, detail="Plan block not found")
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Plan block fields cannot be null")
    if {'start_at', 'end_at'} & changes.keys() or changes.get('status') == 'planned':
        await validate_placement(session, user_id, block.task_id, changes.get('start_at', block.start_at),
                                 changes.get('end_at', block.end_at), block.id)
    moved = 'start_at' in changes and changes['start_at'] != _utc(block.start_at)
    for key, value in changes.items():
        setattr(block, key, value)
    if 'start_at' in changes:
        block.plan_date = await local_plan_date(session, user_id, block.start_at)
    if block.end_at <= block.start_at:
        raise HTTPException(status_code=422, detail="end_at must be after start_at")
    if moved:
        await record_block_move(session, user_id, block)
    await session.commit()
    await session.refresh(block)
    return output(block)

