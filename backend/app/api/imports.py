from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..schemas import TaskCreate
from ..services import syllabus_import

router = APIRouter(prefix='/api/import/syllabus', tags=['import'])


class ExtractRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=200_000)
    # base64 of an 8 MB PDF is about 11.2 million characters.
    pdf_base64: Optional[str] = Field(default=None, max_length=11_200_000)
    client_tz: str = Field(default='UTC', max_length=64)


class SaveRequest(BaseModel):
    tasks: list[TaskCreate] = Field(min_length=1, max_length=syllabus_import.MAX_PROPOSALS)
    plan: bool = True


async def _timezone(session, user_id, client_tz: str) -> str:
    from ..services.planning_service import active_preferences
    values = await active_preferences(session, user_id)
    name = (values.get('timezone') or {}).get('name') or client_tz or 'UTC'
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail='Unknown time zone')
    return name


@router.post('/extract')
async def extract(request: ExtractRequest, session: AsyncSession = Depends(get_session),
                  user_id=Depends(current_user_id)) -> dict:
    """Read a syllabus and return task proposals. Nothing is saved."""
    tz_name = await _timezone(session, user_id, request.client_tz)
    try:
        source = syllabus_import.read_source(request.text, request.pdf_base64)
    except syllabus_import.ImportInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from ..services.llm_client import configured_llm
    result = await syllabus_import.propose(configured_llm(), source, now=datetime.now(timezone.utc), tz_name=tz_name)
    return {**result, 'timezone': tz_name}


@router.post('/save')
async def save(request: SaveRequest, session: AsyncSession = Depends(get_session),
               user_id=Depends(current_user_id)) -> dict:
    """Create the reviewed tasks as one batch (one Undo) and rebuild the plan."""
    result = await syllabus_import.save_proposals(session, user_id, request.tasks, plan=request.plan)
    await session.commit()
    return result


@router.post('/{batch_id}/undo')
async def undo(batch_id: UUID, session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    result = await syllabus_import.undo_import(session, user_id, batch_id)
    await session.commit()
    return result
