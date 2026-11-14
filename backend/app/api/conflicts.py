from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import Conflict
from ..schemas_conflicts import ConflictCreate, ConflictResolve

router = APIRouter(prefix="/api/conflicts", tags=["capacity"])


def output(row: Conflict) -> dict:
    return {"id": str(row.id), "deadline_at": row.deadline_at, "needed_min": row.needed_min,
            "free_min": row.free_min, "shortfall_min": row.needed_min - row.free_min,
            "task_ids": row.task_ids, "options": row.options, "status": row.status}


@router.get("")
async def list_conflicts(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> list[dict]:
    rows = (await session.execute(select(Conflict).where(Conflict.user_id == user_id, Conflict.status == "open").order_by(Conflict.deadline_at))).scalars().all()
    return [output(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conflict(payload: ConflictCreate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    row = Conflict(user_id=user_id, **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return output(row)


@router.post("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: UUID, payload: ConflictResolve, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    row = (await session.execute(select(Conflict).where(Conflict.id == conflict_id, Conflict.user_id == user_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    allowed = {str(option.get("type")) for option in row.options}
    if payload.option_type not in allowed:
        raise HTTPException(status_code=422, detail="Unknown conflict option")
    raise HTTPException(status_code=501, detail="Resolution simulation and plan application are not implemented; conflict remains open")

