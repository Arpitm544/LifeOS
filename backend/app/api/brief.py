from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..db import get_session
from ..services.brief_service import compose, load_brief_data, translate

router = APIRouter(prefix='/api/brief', tags=['planning'])


@router.get('')
async def brief(language: Optional[str] = Query(default=None, pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$'),
                name: str = Query(default='', max_length=40),
                session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    """Morning brief and proactive nudges. Read-only; each nudge names one action the app can take."""
    data = await load_brief_data(session, user_id, now=datetime.now(timezone.utc))
    result = compose(data, name=' '.join(name.split()))
    if language and not language.startswith('en'):
        # Release the connection while the (optional) translation call runs.
        await session.commit()
        from ..services.llm_client import configured_llm
        result = await translate(result, language, configured_llm())
    return result
