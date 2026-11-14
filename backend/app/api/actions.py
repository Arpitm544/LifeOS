from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..services.domain_service import undo_logged_action
from ..models import ActionLog
from sqlalchemy import select
from datetime import timedelta

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get('')
async def recent_actions(session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    rows = (await session.execute(select(ActionLog).where(ActionLog.user_id == user_id)
        .order_by(ActionLog.created_at.desc()).limit(50))).scalars().all()
    return [{'action_id': str(row.id), 'batch_id': str(row.batch_id) if row.batch_id else None,
        'entity': row.entity, 'action_type': row.action_type, 'undone_at': row.undone_at,
        'undo_until': row.created_at + timedelta(seconds=10)} for row in rows]


@router.post('/batches/{batch_id}/undo')
async def undo_batch(batch_id: UUID, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)):
    rows = (await session.execute(select(ActionLog).where(ActionLog.user_id == user_id,
        ActionLog.batch_id == batch_id).order_by(ActionLog.created_at.desc()).with_for_update())).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail='Batch not found')
    for row in rows:
        await undo_logged_action(session, user_id, row.id)
    await session.commit()
    return {'undone': True, 'count': len(rows)}


@router.post("/{action_id}/undo")
async def undo(action_id: UUID, session: AsyncSession = Depends(get_session), user_id: UUID = Depends(current_user_id)) -> dict[str, bool]:
    row = (await session.execute(select(ActionLog).where(ActionLog.id == action_id,
        ActionLog.user_id == user_id))).scalar_one_or_none()
    if row is not None and row.batch_id is not None:
        raise HTTPException(status_code=409, detail='Undo a batch as a single operation')
    await undo_logged_action(session, user_id, action_id)
    await session.commit()
    return {"undone": True}

