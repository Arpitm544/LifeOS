"""Google Calendar sync with Google mocked: OAuth state, token handling, event mapping, sync diffing, disconnect."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app import config
from app.models import Base, Event, GoogleConnection
from app.services import google_calendar as g

OWNER = 'user_google'
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
UTC = ZoneInfo('UTC')


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    values = SimpleNamespace(google_client_id='cid', google_client_secret='secret', token_encryption_key=Fernet.generate_key().decode(),
                             google_redirect_uri='http://127.0.0.1:8000/api/google/callback')
    monkeypatch.setattr(g, 'get_settings', lambda: values)
    return values


def gevent(id, summary='Standup', start='2026-11-20T10:00:00Z', end='2026-11-20T11:00:00Z', **extra):
    return {'id': id, 'summary': summary, 'start': {'dateTime': start}, 'end': {'dateTime': end}, **extra}


def test_state_round_trip_expiry_and_tampering():
    state = g.make_state(OWNER)
    assert g.read_state(state) == OWNER
    with pytest.raises(g.GoogleError):
        g.read_state(g.make_state(OWNER, now=datetime(2020, 1, 1, tzinfo=timezone.utc)))  # expired
    with pytest.raises(g.GoogleError):
        g.read_state(state[:-3] + 'abc')
    with pytest.raises(g.GoogleError):
        g.read_state('not-a-token')


def test_authorization_url_is_read_only_offline_and_carries_state(settings):
    url = g.authorization_url(OWNER)
    assert 'calendar.readonly' in url and 'access_type=offline' in url and 'prompt=consent' in url
    assert 'client_id=cid' in url and 'state=' in url
    settings.google_client_id = ''
    with pytest.raises(g.NotConfigured):
        g.authorization_url(OWNER)


def test_refresh_token_is_encrypted_and_unreadable_with_another_key(settings):
    secret = g.encrypt('1//refresh')
    assert '1//refresh' not in secret and g.decrypt(secret) == '1//refresh'
    settings.token_encryption_key = Fernet.generate_key().decode()
    with pytest.raises(g.Revoked):
        g.decrypt(secret)


def test_to_event_maps_timed_all_day_and_skips_non_busy():
    zone = ZoneInfo('Asia/Kolkata')
    timed = g.to_event(gevent('a', start='2026-11-20T15:30:00+05:30', end='2026-11-20T16:30:00+05:30', location=' Room 4 '), zone)
    assert timed['start_at'] == datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc) and timed['location'] == 'Room 4'
    allday = g.to_event({'id': 'd', 'summary': 'Holiday', 'start': {'date': '2026-11-25'}, 'end': {'date': '2026-11-26'}}, zone)
    assert allday['start_at'] == datetime(2026, 11, 24, 18, 30, tzinfo=timezone.utc)
    assert g.to_event(gevent('b', summary=''), zone)['title'] == 'Busy'
    for skipped in (gevent('c', status='cancelled'), gevent('c', transparency='transparent'),
                    gevent('c', attendees=[{'self': True, 'responseStatus': 'declined'}]),
                    gevent('c', start='2026-11-20T11:00:00Z', end='2026-11-20T10:00:00Z'), {'summary': 'no id'}):
        assert g.to_event(skipped, zone) is None


def make_http(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run_with_session(body):
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await body(session)
        finally:
            await engine.dispose()
    asyncio.run(run())


def google_handler(events, calls=None, token_error=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url).split('?')[0])
        if request.url.host == 'oauth2.googleapis.com' and request.url.path == '/token':
            if token_error:
                return httpx.Response(400, json={'error': token_error})
            return httpx.Response(200, json={'access_token': 'at', 'refresh_token': 'rt', 'scope': g.SCOPE})
        if request.url.path.endswith('/events'):
            assert request.headers['authorization'] == 'Bearer at'
            return httpx.Response(200, json={'items': events() if callable(events) else events})
        return httpx.Response(200, json={})
    return handler


def test_exchange_code_requires_refresh_token_and_calendar_scope():
    async def run():
        async with make_http(google_handler([])) as http:
            assert await g.exchange_code(http, 'code') == 'rt'
        async with make_http(lambda r: httpx.Response(200, json={'access_token': 'x', 'scope': g.SCOPE})) as http:
            with pytest.raises(g.GoogleError):
                await g.exchange_code(http, 'code')
        async with make_http(lambda r: httpx.Response(200, json={'refresh_token': 'x', 'scope': 'email'})) as http:
            with pytest.raises(g.GoogleError):
                await g.exchange_code(http, 'code')
    asyncio.run(run())


def test_sync_creates_updates_removes_and_is_idempotent():
    current = [gevent('e1'), gevent('e2', summary='Lab', start='2026-11-21T09:00:00Z', end='2026-11-21T10:00:00Z')]

    async def body(session):
        await g.save_connection(session, OWNER, 'rt')
        async with make_http(google_handler(lambda: current)) as http:
            first = await g.sync_user(session, OWNER, http, now=NOW)
            assert (first['created'], first['updated'], first['removed']) == (2, 0, 0)
            again = await g.sync_user(session, OWNER, http, now=NOW)
            assert (again['created'], again['updated'], again['removed']) == (0, 0, 0)
            current[0] = gevent('e1', summary='Standup moved', start='2026-11-20T12:00:00Z', end='2026-11-20T12:30:00Z')
            del current[1]
            third = await g.sync_user(session, OWNER, http, now=NOW)
            assert (third['created'], third['updated'], third['removed']) == (0, 1, 1)
        rows = {r.external_id: r for r in (await session.execute(select(Event))).scalars()}
        assert rows['e1'].title == 'Standup moved' and rows['e1'].source == 'gcal' and not rows['e1'].cancelled
        assert rows['e2'].cancelled is True
        # An event that returns is revived rather than duplicated.
        current.append(gevent('e2', summary='Lab', start='2026-11-21T09:00:00Z', end='2026-11-21T10:00:00Z'))
        async with make_http(google_handler(lambda: current)) as http:
            back = await g.sync_user(session, OWNER, http, now=NOW)
        assert back['updated'] == 1
        assert len((await session.execute(select(Event))).scalars().all()) == 2
        connection = (await session.execute(select(GoogleConnection))).scalar_one()
        assert connection.last_synced_at is not None and connection.last_error is None
    run_with_session(body)


def test_sync_never_touches_manual_or_ics_events():
    async def body(session):
        await g.save_connection(session, OWNER, 'rt')
        session.add(Event(user_id=OWNER, title='Mine', start_at=NOW + timedelta(days=2), end_at=NOW + timedelta(days=2, hours=1), source='manual'))
        session.add(Event(user_id=OWNER, title='Imported', start_at=NOW + timedelta(days=3), end_at=NOW + timedelta(days=3, hours=1),
                          source='ics', external_id='ics-1'))
        await session.flush()
        async with make_http(google_handler([])) as http:
            result = await g.sync_user(session, OWNER, http, now=NOW)
        assert result['removed'] == 0
        assert all(not r.cancelled for r in (await session.execute(select(Event))).scalars())
    run_with_session(body)


def test_revoked_access_is_reported_and_remembered():
    async def body(session):
        await g.save_connection(session, OWNER, 'rt')
        async with make_http(google_handler([], token_error='invalid_grant')) as http:
            with pytest.raises(g.Revoked):
                await g.sync_user(session, OWNER, http, now=NOW)
        connection = (await session.execute(select(GoogleConnection))).scalar_one()
        assert 'Reconnect' in connection.last_error
        assert 'rt' not in connection.refresh_token_enc  # stored encrypted
    run_with_session(body)


def test_disconnect_revokes_and_can_keep_or_remove_events():
    async def body(session):
        await g.save_connection(session, OWNER, 'rt')
        calls = []
        async with make_http(google_handler([gevent('e1')], calls)) as http:
            await g.sync_user(session, OWNER, http, now=NOW)
            kept = await g.disconnect(session, OWNER, http, remove_events=False)
        assert kept == {'disconnected': True, 'removed': 0}
        assert any(c.endswith('/revoke') for c in calls)
        assert (await session.execute(select(GoogleConnection))).first() is None
        assert [r.cancelled for r in (await session.execute(select(Event))).scalars()] == [False]
        await g.save_connection(session, OWNER, 'rt')
        async with make_http(google_handler([])) as http:
            removed = await g.disconnect(session, OWNER, http, remove_events=True)
        assert removed['removed'] == 1
        assert [r.cancelled for r in (await session.execute(select(Event))).scalars()] == [True]
    run_with_session(body)


def test_callback_route_binds_connection_to_the_state_user_and_rejects_bad_state(monkeypatch):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import google as api

    loop = asyncio.new_event_loop()
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    loop.run_until_complete(setup())
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def fake_user_session(user_id):
        async with factory() as session:
            await session.execute(select(1))  # like the real one, a statement runs first and begins the transaction
            yield session
    monkeypatch.setattr(api, 'user_session', fake_user_session)
    monkeypatch.setattr(api.gcal, 'new_client', lambda: make_http(google_handler([gevent('e1')])))
    monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(frontend_url='http://localhost:3000'))
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app, follow_redirects=False) as client:
        def outcome(response):
            assert response.status_code == 303
            return response.headers['location'].split('google=')[1]
        assert outcome(client.get('/api/google/callback', params={'error': 'access_denied'})) == 'denied'
        assert outcome(client.get('/api/google/callback', params={'code': 'c', 'state': 'forged'})) == 'expired'
        async def no_scope(http, code):
            raise api.gcal.ScopeNotGranted('Calendar access was not granted.')
        real_exchange = api.gcal.exchange_code
        monkeypatch.setattr(api.gcal, 'exchange_code', no_scope)
        assert outcome(client.get('/api/google/callback', params={'code': 'c', 'state': g.make_state(OWNER)})) == 'no_scope'
        monkeypatch.setattr(api.gcal, 'exchange_code', real_exchange)
        assert outcome(client.get('/api/google/callback', params={'code': 'c', 'state': g.make_state(OWNER)})) == 'connected'

    async def check():
        async with factory() as session:
            connection = (await session.execute(select(GoogleConnection))).scalar_one()
            assert connection.user_id == OWNER and connection.last_synced_at is not None
            assert [e.external_id for e in (await session.execute(select(Event))).scalars()] == ['e1']
        await engine.dispose()
    loop.run_until_complete(check())


def test_callback_is_reachable_without_a_bearer_token_but_other_google_routes_are_not():
    """Google's redirect carries no sign-in token; the rate-limit middleware must let only the callback through."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import google as api
    from app.rate_limit import RateLimitMiddleware, SlidingWindowLimiter
    app = FastAPI()
    app.include_router(api.router)
    app.add_middleware(RateLimitMiddleware, limiter=SlidingWindowLimiter())
    with TestClient(app, follow_redirects=False) as client:
        denied = client.get('/api/google/callback', params={'error': 'access_denied'})
        assert denied.status_code == 303 and denied.headers['location'].endswith('google=denied')
        assert client.get('/api/google/status').status_code == 401
        assert client.post('/api/google/sync').status_code == 401


def test_misconfigured_client_is_reported_as_setup_problem_not_reconnect():
    async def body(session):
        await g.save_connection(session, OWNER, 'rt')
        async with make_http(google_handler([], token_error='invalid_client')) as http:
            with pytest.raises(g.NotConfigured):
                await g.sync_user(session, OWNER, http, now=NOW)
        connection = (await session.execute(select(GoogleConnection))).scalar_one()
        assert 'client ID or secret' in connection.last_error
        assert not g.needs_reconnect(connection.last_error)
        assert g.needs_reconnect(g.REVOKED_MESSAGE)
    run_with_session(body)
