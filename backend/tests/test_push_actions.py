"""Push notification buttons (PRD F3.2): signed per-reminder tokens and the payload the service worker reads."""
from types import SimpleNamespace
from uuid import uuid4

from app.services.chat_orchestrator import SPOKEN_MAX_WORDS, spoken_version
from app.services.push_service import notification_payload
from app.services.push_tokens import TOKEN_TTL_SECONDS, sign_action_token, verify_action_token

SETTINGS = SimpleNamespace(push_action_secret='', vapid_private_key='test-vapid-key', public_api_url='https://api.example.com/')


def test_token_round_trip_is_bound_to_one_reminder_and_user():
    token = sign_action_token(SETTINGS, reminder_id='r1', user_id='user_a', now=1000)
    assert verify_action_token(SETTINGS, token, reminder_id='r1', now=1001) == 'user_a'
    assert verify_action_token(SETTINGS, token, reminder_id='r2', now=1001) is None


def test_token_expires_and_rejects_tampering():
    token = sign_action_token(SETTINGS, reminder_id='r1', user_id='user_a', now=1000)
    assert verify_action_token(SETTINGS, token, reminder_id='r1', now=1000 + TOKEN_TTL_SECONDS + 1) is None
    body, signature = token.split('.')
    assert verify_action_token(SETTINGS, body + '.' + signature[:-2] + 'xx', reminder_id='r1', now=1001) is None
    other = SimpleNamespace(push_action_secret='different', vapid_private_key='', public_api_url='')
    assert verify_action_token(other, token, reminder_id='r1', now=1001) is None
    assert verify_action_token(SETTINGS, 'garbage', reminder_id='r1') is None


def test_no_secret_means_no_token():
    empty = SimpleNamespace(push_action_secret='', vapid_private_key='', public_api_url='')
    assert sign_action_token(empty, reminder_id='r1', user_id='u') is None
    assert verify_action_token(empty, 'a.b', reminder_id='r1') is None


def test_payload_carries_action_url_and_token_for_task_reminders():
    reminder = SimpleNamespace(id=uuid4(), user_id='user_a', item_type='task', item_id=uuid4(), kind='due_soon', message='Report due in 2 h')
    payload = notification_payload(reminder, settings=SETTINGS)
    assert [a['action'] for a in payload['actions']] == ['done', 'snooze_15', 'snooze_60']
    assert payload['action_url'] == f'https://api.example.com/api/push-actions/{reminder.id}'
    assert verify_action_token(SETTINGS, payload['action_token'], reminder_id=str(reminder.id)) == 'user_a'
    assert payload['url'] == f'/task/{reminder.item_id}'


def test_payload_without_settings_or_for_events_has_no_token():
    task = SimpleNamespace(id=uuid4(), user_id='u', item_type='task', item_id=uuid4(), kind='start_now', message=None)
    assert 'action_token' not in notification_payload(task)
    event = SimpleNamespace(id=uuid4(), user_id='u', item_type='event', item_id=uuid4(), kind='event', message='Sync')
    payload = notification_payload(event, settings=SETTINGS)
    assert payload['actions'] == [] and 'action_token' not in payload


def test_spoken_reply_is_short_and_plain():
    assert spoken_version('Added 3 tasks. Thursday is tight.') == 'Added 3 tasks. Thursday is tight.'
    long = spoken_version('First sentence here. ' + ' '.join(['word'] * 40) + '.')
    assert long == 'First sentence here.'
    cut = spoken_version(' '.join(['word'] * 40))
    assert len(cut.split()) == SPOKEN_MAX_WORDS
    plain = spoken_version('**Due** at 2026-11-19T09:00:00+05:30 → see [card]')
    assert '*' not in plain and '2026' not in plain and '[' not in plain
    assert spoken_version('') == 'Okay.'


def test_rate_limiter_authenticates_push_actions_by_token(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import config
    from app.rate_limit import RateLimitMiddleware, SlidingWindowLimiter

    settings = SimpleNamespace(api_rate_limit=300, chat_rate_limit=30, push_action_secret='s', vapid_private_key='')
    monkeypatch.setattr(config, 'get_settings', lambda: settings)
    application = FastAPI()
    application.add_middleware(RateLimitMiddleware, limiter=SlidingWindowLimiter())

    @application.post('/api/push-actions/{reminder_id}')
    async def act(reminder_id: str):
        return {'ok': True}

    token = sign_action_token(settings, reminder_id='r1', user_id='user_a')
    with TestClient(application) as client:
        assert client.post('/api/push-actions/r1', headers={'X-Push-Token': token}).status_code == 200
        assert client.post('/api/push-actions/r2', headers={'X-Push-Token': token}).status_code == 401
        assert client.post('/api/push-actions/r1').status_code == 401
