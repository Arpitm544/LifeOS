from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user_id
from ..config import get_settings
from ..db import get_session, user_session
from ..models import GoogleConnection
from ..services import google_calendar as gcal

log = logging.getLogger('lifeos.google')
router = APIRouter(prefix='/api/google', tags=['google'])


def _fail(exc: gcal.GoogleError) -> HTTPException:
    if isinstance(exc, gcal.NotConfigured):
        return HTTPException(status_code=503, detail={'code': 'google_not_configured', 'message': str(exc)})
    if isinstance(exc, gcal.Revoked):
        return HTTPException(status_code=409, detail={'code': 'google_reconnect', 'message': str(exc)})
    return HTTPException(status_code=502, detail=str(exc))


@router.get('/status')
async def status(session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    row = (await session.execute(select(GoogleConnection).where(GoogleConnection.user_id == user_id))).scalar_one_or_none()
    return {'configured': gcal.configured(), 'connected': row is not None,
            'last_synced_at': row.last_synced_at if row else None, 'last_error': row.last_error if row else None,
            'needs_reconnect': bool(row) and gcal.needs_reconnect(row.last_error)}


@router.post('/connect')
async def connect(user_id=Depends(current_user_id)) -> dict:
    """The Google consent URL for the signed-in user. The browser is sent there by the app."""
    try:
        return {'url': gcal.authorization_url(user_id)}
    except gcal.GoogleError as exc:
        raise _fail(exc)


@router.get('/callback')
async def callback(code: str = Query(default=''), state: str = Query(default=''), error: str = Query(default='')):
    """Google redirects the browser here. There is no bearer token: the signed `state` identifies the user."""
    back = get_settings().frontend_url.rstrip('/') + '/import/calendar'

    def done(result: str) -> RedirectResponse:
        return RedirectResponse(back + '?' + urlencode({'google': result}), status_code=303)
    if error or not code:
        return done('denied')
    try:
        user_id = gcal.read_state(state)
    except gcal.GoogleError:
        return done('expired')
    try:
        async with gcal.new_client() as http:
            refresh = await gcal.exchange_code(http, code)
            # user_session has already begun a transaction (it upserts the user row), so commit rather than begin().
            async with user_session(user_id) as session:
                await gcal.save_connection(session, user_id, refresh)
                await session.commit()
            async with user_session(user_id) as session:
                await gcal.sync_user(session, user_id, http)
                await session.commit()
    except gcal.GoogleError as exc:
        log.warning('google callback: %s', exc)
        if isinstance(exc, gcal.ScopeNotGranted):
            return done('no_scope')
        if isinstance(exc, gcal.NotConfigured):
            return done('not_configured')
        # The link was saved before the first sync; a sync problem is shown on the page, not as a failed connect.
        return done('connected_sync_failed' if await _connected(user_id) else 'error')
    except Exception:
        log.exception('google callback failed')
        return done('error')
    return done('connected')


async def _connected(user_id) -> bool:
    try:
        async with user_session(user_id) as session:
            return (await session.execute(select(GoogleConnection.id).where(GoogleConnection.user_id == user_id))).first() is not None
    except Exception:
        return False


@router.post('/sync')
async def sync(session: AsyncSession = Depends(get_session), user_id=Depends(current_user_id)) -> dict:
    try:
        async with gcal.new_client() as http:
            result = await gcal.sync_user(session, user_id, http)
    except gcal.GoogleError as exc:
        await session.commit()  # keep last_error so the page can show it
        raise _fail(exc)
    await session.commit()
    return result


@router.delete('/disconnect')
async def disconnect(remove_events: bool = True, session: AsyncSession = Depends(get_session),
                     user_id=Depends(current_user_id)) -> dict:
    async with gcal.new_client() as http:
        result = await gcal.disconnect(session, user_id, http, remove_events=remove_events)
    await session.commit()
    return result
