from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import Conflict, Task
from ..schemas_conflicts import ConflictCreate, ConflictResolve
from ..services.conflict_service import resolve, simulate_options

router = APIRouter(prefix="/api/conflicts", tags=["capacity"])


def output(row: Conflict, titles: dict | None = None) -> dict:
    result = {"id": str(row.id), "deadline_at": row.deadline_at, "needed_min": row.needed_min,
              "free_min": row.free_min, "shortfall_min": row.needed_min - row.free_min,
              "task_ids": row.task_ids, "options": row.options, "status": row.status}
    if titles is not None:
        result["tasks"] = [{"id": identity, "title": titles.get(identity)} for identity in row.task_ids]
    return result


async def _titles(session, user_id) -> dict:
    rows = (await session.execute(select(Task.id, Task.title).where(Task.user_id == user_id))).all()
    return {str(identity): title for identity, title in rows}


async def _owned(session, user_id, conflict_id: UUID) -> Conflict:
    row = (await session.execute(select(Conflict).where(Conflict.id == conflict_id,
        Conflict.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return row


@router.get("")
async def list_conflicts(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> list[dict]:
    rows = (await session.execute(select(Conflict).where(Conflict.user_id == user_id, Conflict.status == "open").order_by(Conflict.deadline_at))).scalars().all()
    titles = await _titles(session, user_id)
    return [output(row, titles) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conflict(payload: ConflictCreate, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    row = Conflict(user_id=user_id, **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return output(row)


@router.get("/{conflict_id}/options")
async def conflict_options(conflict_id: UUID, session: AsyncSession = Depends(get_session),
                           user_id: UUID = Depends(current_user_id)) -> dict:
    """Simulated outcomes with timeline previews; nothing is written."""
    row = await _owned(session, user_id, conflict_id)
    return {"conflict": output(row, await _titles(session, user_id)),
            "options": await simulate_options(session, user_id, row)}


@router.post("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: UUID, payload: ConflictResolve, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict:
    row = await _owned(session, user_id, conflict_id)
    if row.status != 'open':
        raise HTTPException(status_code=409, detail=f"Conflict is already {row.status}")
    allowed = {str(option.get("type")) for option in row.options}
    if payload.option_type not in allowed:
        raise HTTPException(status_code=422, detail="Unknown conflict option")
    result = await resolve(session, user_id, row, payload.option_type)
    await session.commit()
    return result

