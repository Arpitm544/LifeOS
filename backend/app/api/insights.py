from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..models import Suggestion
from ..schemas_insights import InsightsResponse
from ..services.insight_service import apply_suggestion, compute_user_insights, latest_suggestions
from ..services.llm_client import configured_llm

router = APIRouter(prefix="/api/insights", tags=["insights"])


def suggestion_out(row: Suggestion) -> dict:
    return {'id': str(row.id), 'type': row.type, 'text': row.text, 'payload': row.payload, 'status': row.status}


@router.get("", response_model=InsightsResponse)
async def insights(session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> InsightsResponse:
    now = datetime.now(timezone.utc)
    data = await compute_user_insights(session, user_id, now=now)
    rows = await latest_suggestions(session, user_id, data, now=now, llm=configured_llm())
    await session.commit()
    return InsightsResponse(**data, suggestions=[suggestion_out(row) for row in rows])


async def _owned(session, user_id, suggestion_id: UUID) -> Suggestion:
    row = (await session.execute(select(Suggestion).where(Suggestion.id == suggestion_id,
        Suggestion.user_id == user_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail='Suggestion not found')
    if row.status != 'active':
        raise HTTPException(status_code=409, detail=f'Suggestion already {row.status}')
    return row


@router.post('/suggestions/{suggestion_id}/apply')
async def apply(suggestion_id: UUID, session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    row = await _owned(session, user_id, suggestion_id)
    result = await apply_suggestion(session, user_id, row)
    await session.commit()
    return result


@router.post('/suggestions/{suggestion_id}/dismiss')
async def dismiss(suggestion_id: UUID, session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    row = await _owned(session, user_id, suggestion_id)
    row.status = 'dismissed'
    await session.commit()
    return suggestion_out(row)
