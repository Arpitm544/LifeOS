"""Read-only Google Calendar sync: OAuth (authorization-code flow) and a one-way copy of busy time into LifeOS.

Only the `calendar.readonly` scope is requested. LifeOS never writes to Google. The refresh token is encrypted
at rest, and the OAuth `state` is a short-lived signed token that carries the user id, so the unauthenticated
callback can only ever attach a connection to the user who started the flow.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from ..config import get_settings

log = logging.getLogger('lifeos.google')

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'
SOURCE = 'gcal'
STATE_AUDIENCE = 'lifeos-google-oauth'
STATE_TTL = timedelta(minutes=10)
WINDOW_BEHIND = timedelta(days=1)
WINDOW_AHEAD = timedelta(days=60)
PAGE_SIZE = 250
MAX_PAGES = 4
MAX_EVENT_LENGTH = timedelta(days=14)


class GoogleError(Exception):
    """A failure whose message is safe to show the user."""


class NotConfigured(GoogleError):
    pass


class Revoked(GoogleError):
    """Google no longer accepts the stored refresh token; the user must reconnect."""


REVOKED_MESSAGE = 'Google access was removed. Reconnect Google Calendar.'
UNREADABLE_MESSAGE = 'The saved Google connection can no longer be read. Reconnect Google Calendar.'
BAD_CLIENT_MESSAGE = ("Google rejected this server's client ID or secret. "
                      'Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the backend settings.')


def needs_reconnect(last_error: Optional[str]) -> bool:
    return last_error in (REVOKED_MESSAGE, UNREADABLE_MESSAGE)


def configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret and s.token_encryption_key)


def _require_configured():
    if not configured():
        raise NotConfigured('Google Calendar is not set up on this server yet.')


def _fernet() -> Fernet:
    try:
        return Fernet(get_settings().token_encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise NotConfigured('TOKEN_ENCRYPTION_KEY is not a valid Fernet key.') from exc


def encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise Revoked(UNREADABLE_MESSAGE) from exc


def _state_key() -> str:
    return hashlib.sha256(('lifeos-state|' + get_settings().token_encryption_key).encode()).hexdigest()


def make_state(user_id: str, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    claims = {'sub': user_id, 'aud': STATE_AUDIENCE, 'iat': int(now.timestamp()),
              'exp': int((now + STATE_TTL).timestamp()), 'nonce': secrets.token_urlsafe(8)}
    return jwt.encode(claims, _state_key(), algorithm='HS256')


def read_state(state: str) -> str:
    try:
        claims = jwt.decode(state, _state_key(), algorithms=['HS256'], audience=STATE_AUDIENCE)
    except JWTError as exc:
        raise GoogleError('That Google sign-in link expired. Start the connection again.') from exc
    return str(claims['sub'])


def authorization_url(user_id: str) -> str:
    _require_configured()
    s = get_settings()
    params = {'client_id': s.google_client_id, 'redirect_uri': s.google_redirect_uri, 'response_type': 'code',
              'scope': SCOPE, 'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'false',
              'state': make_state(user_id)}
    return AUTH_URL + '?' + urlencode(params)


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15)


async def exchange_code(http: httpx.AsyncClient, code: str) -> str:
    """Trade the one-time code for a refresh token."""
    _require_configured()
    s = get_settings()
    response = await http.post(TOKEN_URL, data={'code': code, 'client_id': s.google_client_id,
        'client_secret': s.google_client_secret, 'redirect_uri': s.google_redirect_uri, 'grant_type': 'authorization_code'})
    body = _json(response)
    if body.get('error') in ('invalid_client', 'unauthorized_client'):
        raise NotConfigured(BAD_CLIENT_MESSAGE)
    if response.status_code != 200 or not body.get('refresh_token'):
        raise GoogleError('Google did not complete the connection. Try again.')
    if SCOPE not in str(body.get('scope', '')).split():
        raise GoogleError('Calendar access was not granted. Connect again and allow calendar access.')
    return body['refresh_token']


async def access_token(http: httpx.AsyncClient, refresh_token: str) -> str:
    _require_configured()
    s = get_settings()
    response = await http.post(TOKEN_URL, data={'client_id': s.google_client_id, 'client_secret': s.google_client_secret,
        'refresh_token': refresh_token, 'grant_type': 'refresh_token'})
    body = _json(response)
    if body.get('error') == 'invalid_grant':
        raise Revoked(REVOKED_MESSAGE)
    if body.get('error') in ('invalid_client', 'unauthorized_client'):
        raise NotConfigured(BAD_CLIENT_MESSAGE)
    if response.status_code != 200 or not body.get('access_token'):
        raise GoogleError('Could not reach Google Calendar. Try again in a moment.')
    return body['access_token']


async def revoke(http: httpx.AsyncClient, refresh_token: str) -> None:
    """Best effort: tell Google to drop the grant. Failure must not block disconnecting."""
    try:
        await http.post(REVOKE_URL, data={'token': refresh_token})
    except httpx.HTTPError:
        log.warning('google revoke failed')


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


async def fetch_events(http: httpx.AsyncClient, token: str, start: datetime, end: datetime) -> tuple[list[dict], bool]:
    """Expanded (single) instances in the window, so recurrence and exceptions are Google's own answer."""
    items: list[dict] = []
    params = {'timeMin': start.isoformat().replace('+00:00', 'Z'), 'timeMax': end.isoformat().replace('+00:00', 'Z'),
              'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': PAGE_SIZE, 'showDeleted': 'false'}
    for _ in range(MAX_PAGES):
        response = await http.get(EVENTS_URL, params=params, headers={'Authorization': f'Bearer {token}'})
        if response.status_code in (401, 403):
            raise Revoked(REVOKED_MESSAGE)
        if response.status_code != 200:
            raise GoogleError('Could not read your Google Calendar. Try again in a moment.')
        body = _json(response)
        items.extend(item for item in body.get('items', []) if isinstance(item, dict))
        if not body.get('nextPageToken'):
            return items, False
        params = {**params, 'pageToken': body['nextPageToken']}
    return items, True


def _moment(value: dict, zone: ZoneInfo) -> Optional[datetime]:
    try:
        if value.get('dateTime'):
            moment = datetime.fromisoformat(value['dateTime'].replace('Z', '+00:00'))
            return moment if moment.tzinfo else moment.replace(tzinfo=zone)
        if value.get('date'):  # all-day: busy from local midnight
            return datetime.combine(date.fromisoformat(value['date']), time.min, tzinfo=zone)
    except (ValueError, TypeError):
        return None
    return None


def to_event(item: dict, zone: ZoneInfo) -> Optional[dict]:
    """A Google event as LifeOS fields, or None when it is not busy time (cancelled, free, declined, unreadable)."""
    if item.get('status') == 'cancelled' or item.get('transparency') == 'transparent' or not item.get('id'):
        return None
    if any(a.get('self') and a.get('responseStatus') == 'declined' for a in item.get('attendees', []) if isinstance(a, dict)):
        return None
    start, end = _moment(item.get('start') or {}, zone), _moment(item.get('end') or {}, zone)
    if start is None or end is None or end <= start or end - start > MAX_EVENT_LENGTH:
        return None
    location = str(item.get('location') or '').strip()[:200] or None
    return {'external_id': str(item['id'])[:200], 'title': (str(item.get('summary') or '').strip() or 'Busy')[:120],
            'location': location,
            'start_at': start.astimezone(timezone.utc), 'end_at': end.astimezone(timezone.utc)}


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


async def user_timezone(session, user_id) -> str:
    from .planning_service import active_preferences
    return ((await active_preferences(session, user_id)).get('timezone') or {}).get('name') or 'UTC'


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def sync_user(session, user_id, http: httpx.AsyncClient, *, now: Optional[datetime] = None) -> dict:
    """Copy the next 60 days of busy time from Google into LifeOS. Never writes to Google."""
    from sqlalchemy import select
    from ..models import Event, GoogleConnection
    from .domain_service import audit, lock_owner, snapshot
    now = now or datetime.now(timezone.utc)
    connection = (await session.execute(select(GoogleConnection).where(GoogleConnection.user_id == user_id))).scalar_one_or_none()
    if connection is None:
        raise GoogleError('Google Calendar is not connected.')
    zone = _zone(await user_timezone(session, user_id))
    start, end = now - WINDOW_BEHIND, now + WINDOW_AHEAD
    try:
        token = await access_token(http, decrypt(connection.refresh_token_enc))
        raw, truncated = await fetch_events(http, token, start, end)
    except GoogleError as exc:
        connection.last_error = str(exc)[:200]
        await session.flush()
        raise
    wanted = {}
    for item in raw:
        event = to_event(item, zone)
        if event:
            wanted[event['external_id']] = event
    await lock_owner(session, user_id)
    existing = {row.external_id: row for row in (await session.execute(select(Event).where(
        Event.user_id == user_id, Event.source == SOURCE))).scalars()}
    created = updated = removed = 0
    for external_id, fields in wanted.items():
        row = existing.get(external_id)
        if row is None:
            row = Event(user_id=user_id, source=SOURCE, rrule=None, **fields)
            session.add(row)
            await audit(session, user_id, row, None, 'create')
            created += 1
            continue
        changed = (row.cancelled or row.title != fields['title'] or row.location != fields['location']
                   or _utc(row.start_at) != fields['start_at'] or _utc(row.end_at) != fields['end_at'])
        if changed:
            before = snapshot(row)
            row.cancelled, row.title, row.location = False, fields['title'], fields['location']
            row.start_at, row.end_at = fields['start_at'], fields['end_at']
            await audit(session, user_id, row, before, 'update')
            updated += 1
    if not truncated:  # with a partial page set we cannot tell "gone" from "not fetched"
        for external_id, row in existing.items():
            if external_id in wanted or row.cancelled:
                continue
            if _utc(row.end_at) > start and _utc(row.start_at) < end:
                before = snapshot(row)
                row.cancelled = True
                await audit(session, user_id, row, before, 'delete')
                removed += 1
    connection.last_synced_at, connection.last_error = now, None
    note = None
    if created or updated or removed:
        from .planning_service import rebuild_plan
        try:
            await rebuild_plan(session, user_id, days=14)
        except Exception:  # a planning problem must not discard a successful sync
            log.exception('plan rebuild after google sync failed')
            note = 'Events synced, but the plan could not be rebuilt yet.'
    await session.flush()
    return {'created': created, 'updated': updated, 'removed': removed, 'truncated': truncated,
            'last_synced_at': now.isoformat(), 'note': note}


async def save_connection(session, user_id, refresh_token: str) -> None:
    from sqlalchemy import select
    from ..models import GoogleConnection
    row = (await session.execute(select(GoogleConnection).where(GoogleConnection.user_id == user_id))).scalar_one_or_none()
    if row is None:
        session.add(GoogleConnection(user_id=user_id, refresh_token_enc=encrypt(refresh_token)))
    else:
        row.refresh_token_enc, row.last_error = encrypt(refresh_token), None
    await session.flush()


async def disconnect(session, user_id, http: httpx.AsyncClient, *, remove_events: bool) -> dict:
    from sqlalchemy import select
    from ..models import Event, GoogleConnection
    from .domain_service import audit, snapshot
    row = (await session.execute(select(GoogleConnection).where(GoogleConnection.user_id == user_id))).scalar_one_or_none()
    if row is None:
        return {'disconnected': False, 'removed': 0}
    try:
        await revoke(http, decrypt(row.refresh_token_enc))
    except GoogleError:
        pass  # an unreadable token cannot be revoked; still disconnect
    removed = 0
    if remove_events:
        for event in (await session.execute(select(Event).where(Event.user_id == user_id, Event.source == SOURCE,
                                                                Event.cancelled == False))).scalars():  # noqa: E712
            before = snapshot(event)
            event.cancelled = True
            await audit(session, user_id, event, before, 'delete')
            removed += 1
    await session.delete(row)
    await session.flush()
    if removed:
        from .planning_service import rebuild_plan
        try:
            await rebuild_plan(session, user_id, days=14)
        except Exception:
            log.exception('plan rebuild after google disconnect failed')
    return {'disconnected': True, 'removed': removed}
