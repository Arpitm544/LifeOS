"""Executable PRD audit and regression tests for the first remediation step."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import auth, config
from app.main import app
from app.schemas import ChatRequest, TaskCreate
from app.schemas_preferences import RoutineCreate
from app.services.capacity_guard import CapacityTask, check_capacity
from app.services.nlu_validator import CreateTaskCall, validate_create_task
from app.services.reminder_service import move_out_of_quiet_hours
from app.services.scheduler import BusyBlock, SchedulableTask, generate_plan

NOW = datetime(2026, 11, 14, 9, tzinfo=timezone.utc)
OWNER = 'user_2RfWKJREkjKbHZy0Wqa5qrHeAnb'


@pytest.fixture
def settings(monkeypatch):
    value = SimpleNamespace(environment='production', allow_demo_auth=False,
                            clerk_issuer='https://audit.clerk.accounts.dev',
                            clerk_jwks_url='https://audit.clerk.accounts.dev/.well-known/jwks.json',
                            clerk_audience='lifeos-api', clerk_authorized_parties='http://localhost:3000',
                            api_rate_limit=300, chat_rate_limit=30)
    monkeypatch.setattr(auth, 'get_settings', lambda: value)
    monkeypatch.setattr(config, 'get_settings', lambda: value)
    return value


def test_app_health_and_openapi():
    with TestClient(app) as client:
        assert client.get('/health').json() == {'status': 'ok'}
        assert client.get('/openapi.json').status_code == 200


@pytest.mark.parametrize('method,path', [
    ('get', '/api/tasks'), ('post', '/api/chat'), ('get', '/api/today'),
    ('get', '/api/events'), ('get', '/api/preferences'), ('get', '/api/conflicts'),
    ('post', '/api/plan/generate'), ('post', '/api/capacity/check'),
    ('post', '/api/reminders/preview'), ('get', '/api/insights'),
])
def test_api_rejects_anonymous_requests(method, path, settings):
    with TestClient(app) as client:
        response = getattr(client, method)(path)
    assert response.status_code == 401


def test_demo_header_cannot_bypass_production_auth(settings):
    with TestClient(app) as client:
        assert client.get('/api/tasks', headers={'X-Demo-User-Id': OWNER}).status_code == 401


@pytest.mark.parametrize('overrides', [{'exp': 1}, {'sub': 'not-a-clerk-user'}])
def test_invalid_claims_rejected(settings, overrides):
    # Unsupported legacy symmetric tokens must never authenticate a Clerk user.
    token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJub3QtYS1jbGVyay11c2VyIn0.invalid'
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.current_user_id('Bearer ' + token, None))
    assert exc.value.status_code == 401


def test_valid_token_resolves_subject(settings, monkeypatch):
    async def verify(token, configured):
        assert configured is settings
        return OWNER
    monkeypatch.setattr(auth, 'verify_token', verify)
    assert asyncio.run(auth.current_user_id('Bearer token', None)) == OWNER


def test_multiple_tasks_share_free_time_without_overlaps():
    end = NOW + timedelta(hours=3)
    tasks = [SchedulableTask('a', 120, end, 90), SchedulableTask('b', 120, end, 80)]
    blocks, unplaced = generate_plan(tasks=tasks, slots=[BusyBlock(NOW, end)])
    assert sum((b.end - b.start).total_seconds() / 60 for b in blocks) == 180
    assert [task.id for task in unplaced] == ['b']
    assert all(left.end <= right.start for left, right in zip(blocks, blocks[1:]))


@pytest.mark.parametrize('hour,minute', [(23, 0), (0, 30), (6, 45)])
def test_overnight_quiet_hours_move_to_morning(hour, minute):
    moment = NOW.replace(hour=hour, minute=minute)
    adjusted = move_out_of_quiet_hours(moment)
    assert adjusted.hour == 7 and adjusted.minute == 30 and adjusted > moment


def test_deadline_inside_quiet_hours_moves_reminder_earlier():
    moment = NOW.replace(hour=23)
    deadline = moment + timedelta(hours=1)
    assert move_out_of_quiet_hours(moment, deadline=deadline) == moment.replace(hour=22, minute=30)


def test_task_schema_rejects_naive_deadline():
    with pytest.raises(ValidationError):
        TaskCreate(title='Report', deadline_at=datetime(2026, 11, 20))


def test_routine_rejects_malformed_recurrence():
    with pytest.raises(ValidationError):
        RoutineCreate(title='Gym', rrule='not-an-rrule', start_time='not-a-time', duration_min=60)


def test_capacity_cannot_silently_pass_without_supply_for_a_deadline():
    conflicts = check_capacity(tasks=[CapacityTask('a', 'Report', 180, NOW)], free_minutes_until={})
    assert conflicts


def test_unparseable_deadline_phrase_requires_clarification():
    call = CreateTaskCall(title='Report', deadline_iso=NOW + timedelta(days=1),
                          deadline_phrase='the frobnicated moon date')
    assert validate_create_task(call, now=NOW, timezone='UTC')


@pytest.mark.parametrize('rule', ['FREQ=WEEKLY;BYDAY=MO,WE,FR', 'FREQ=DAILY;INTERVAL=2', 'FREQ=MONTHLY;COUNT=3'])
def test_valid_routines_are_preserved(rule):
    routine = RoutineCreate(title='Gym', rrule=rule, start_time='07:30', duration_min=60)
    assert routine.rrule == rule and routine.start_time == '07:30'


@pytest.mark.parametrize('rule', ['FREQ=DAILY;INTERVAL=0', 'FREQ=DAILY;COUNT=-1', 'FREQ=NEVER'])
def test_invalid_recurrence_values_rejected(rule):
    with pytest.raises(ValidationError):
        RoutineCreate(title='Gym', rrule=rule, start_time='07:30', duration_min=60)


@pytest.mark.parametrize('clock', ['24:00', '12:60', '7:30', 'hello'])
def test_routine_time_validation(clock):
    with pytest.raises(ValidationError):
        RoutineCreate(title='Gym', rrule='FREQ=DAILY', start_time=clock, duration_min=60)


def test_chat_timezone_validation():
    assert ChatRequest(text='hello', client_tz='Asia/Kolkata').client_tz == 'Asia/Kolkata'
    with pytest.raises(ValidationError):
        ChatRequest(text='hello', client_tz='Mars/Olympus')


@pytest.mark.parametrize('offset,clarify', [(0, False), (60, False), (61, True)])
def test_dual_parse_one_hour_threshold(offset, clarify):
    call = CreateTaskCall(title='Report', deadline_iso=NOW + timedelta(days=1, minutes=offset),
                          deadline_phrase='tomorrow at 9 am')
    result = validate_create_task(call, now=NOW, timezone='UTC')
    assert bool(result) is clarify


def test_missing_supply_only_affects_missing_deadline():
    later = NOW + timedelta(days=1)
    conflicts = check_capacity(tasks=[CapacityTask('a', 'Report', 180, NOW),
                                     CapacityTask('b', 'Quiz', 30, later)],
                               free_minutes_until={later: 300})
    assert len(conflicts) == 1
    assert conflicts[0].deadline == NOW and conflicts[0].shortfall_min == 180
