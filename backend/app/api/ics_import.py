from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..services import ics_import

router = APIRouter(prefix='/api/import/calendar', tags=['import'])


class ParseRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=3_000_000)
    client_tz: str = Field(default='UTC', max_length=64)


class EventProposal(BaseModel):
    model_config = {'extra': 'forbid'}
    title: str = Field(min_length=1, max_length=120)
    start_at: AwareDatetime
    end_at: AwareDatetime
    location: Optional[str] = Field(default=None, max_length=200)
    rrule: Optional[str] = Field(default=None, max_length=512)
    external_id: str = Field(min_length=1, max_length=200)
    all_day: bool = False

    @model_validator(mode='after')
    def valid_range(self):
        if self.end_at <= self.start_at:
            raise ValueError('end_at must be after start_at')
        return self


class SaveRequest(BaseModel):
    events: list[EventProposal] = Field(min_length=1, max_length=ics_import.MAX_EVENTS)


@router.post('/parse')
async def parse(request: ParseRequest, session: AsyncSession = Depends(get_session),
                user_id=Depends(current_user_id)) -> dict:
    """Read an .ics file and return event proposals. Nothing is saved."""
    from .imports import _timezone
    tz_name = await _timezone(session, user_id, request.client_tz)
    try:
        source = ics_import.read_source(request.text)
    except ics_import.IcsInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {**ics_import.parse_calendar(source, tz_name, datetime.now(timezone.utc)), 'timezone': tz_name}


@router.post('/save')
async def save(request: SaveRequest, session: AsyncSession = Depends(get_session),
               user_id=Depends(current_user_id)) -> dict:
    """Create the reviewed events as one batch (one Undo)."""
    result = await ics_import.save_events(session, user_id, request.events)
    await session.commit()
    return result


@router.post('/{batch_id}/undo')
async def undo(batch_id: UUID, session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    result = await ics_import.undo_import(session, user_id, batch_id)
    await session.commit()
    return result
