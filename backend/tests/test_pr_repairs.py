import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.schemas import TaskCreate, TaskPatch
from app.schemas_capacity import CapacityCheckRequest
from app.schemas_conflicts import ConflictCreate
from app.schemas_events import EventCreate, EventPatch
from app.schemas_plan import PlanGenerateRequest
from app.schemas_plan_blocks import PlanBlockPatch
from app.schemas_reminders import ReminderPreviewRequest
from app.services.analytics_service import CompletedTask, compute_insights
from app.services.chat_orchestrator import handle_chat
from app.services.insight_service import validate_suggestions
from app.services.llm_client import LLMResponse, AnthropicLLMClient, configured_llm
from app.services.nlu_validator import ToolCall
from app.services.priority_engine import calculate_priority
from app.services.recurrence import expand_routine
from app.services.scheduler import BusyBlock, SchedulableTask, build_free_slots, generate_plan
from app.rate_limit import SlidingWindowLimiter
from seed_demo import build_demo

NOW = datetime(2026, 11, 14, 9, tzinfo=timezone.utc)


@pytest.mark.parametrize('model,data', [
    (TaskCreate, {'title': '   '}), (TaskPatch, {'title': '\t'}),
    (TaskCreate, {'title': 'Task', 'recurrence_rrule': 'x' * 513}),
    (PlanBlockPatch, {'statuz': 'done'}),
    (PlanBlockPatch, {'start_at': '2026-11-14T09:00:00'}),
    (ConflictCreate, {'deadline_at': NOW, 'needed_min': 5, 'free_min': 5}),
    (ConflictCreate, {'deadline_at': NOW.replace(tzinfo=None), 'needed_min': 5, 'free_min': 0}),
    (CapacityCheckRequest, {'tasks': [{'id': 'a', 'title': 'a', 'effort_min': 30, 'deadline': NOW.replace(tzinfo=None)}]}),
    (CapacityCheckRequest, {'free_minutes_until': {'2026-11-14T09:00:00': 30}}),
    (PlanGenerateRequest, {'window_start': NOW, 'window_end': NOW.replace(tzinfo=None)}),
    (PlanGenerateRequest, {'window_start': NOW, 'window_end': NOW + timedelta(hours=1),
        'tasks': [{'id': 'a', 'effort_min': 30, 'deadline': NOW, 'priority_score': 0}] * 2}),
    (ReminderPreviewRequest, {'deadline': NOW, 'now': NOW, 'effort_min': 4}),
    (ReminderPreviewRequest, {'deadline': NOW, 'now': NOW, 'effort_min': 601}),
    (EventCreate, {'title': 'a', 'start_at': NOW, 'end_at': NOW + timedelta(hours=1), 'source': 'x' * 17}),
    (EventPatch, {'location': 'x' * 201}), (EventPatch, {'rrule': 'x' * 513}),
])
def test_reject_invalid_boundary_values(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_work_windows_and_input_slots_are_merged():
    end = NOW + timedelta(hours=6)
    slots = build_free_slots(window_start=NOW, window_end=end, working_hours=[(9, 12), (11, 15)], busy=[])
    assert slots == [BusyBlock(NOW, end)]
    blocks, unplaced = generate_plan(tasks=[SchedulableTask('a', 360, end, 90)],
        slots=[BusyBlock(NOW, NOW + timedelta(hours=3)), BusyBlock(NOW + timedelta(hours=2), end)])
    assert not unplaced
    assert sum((block.end - block.start).total_seconds() for block in blocks) == 6 * 3600
    assert all(left.end <= right.start for left, right in zip(blocks, blocks[1:]))
    with pytest.raises(ValueError, match='unique'):
        generate_plan(tasks=[SchedulableTask('a', 30, end, 90)] * 2, slots=slots)


@pytest.mark.parametrize('day', [date(2026, 3, 8), date(2026, 11, 1)])
def test_routine_duration_is_elapsed_time_across_dst(day):
    start = datetime.combine(day, datetime.min.time(), timezone.utc)
    rows = expand_routine('FREQ=DAILY;COUNT=1', '01:30', 120, day, start,
                          start + timedelta(days=2), 'America/New_York')
    assert len(rows) == 1
    assert rows[0]['end_at'] - rows[0]['start_at'] == timedelta(minutes=120)


def test_overdue_urgency_ignores_spare_capacity():
    result = calculate_priority(now=NOW, deadline=NOW - timedelta(hours=1), effort_min=30,
        importance=3, blocking_count=0, created_at=NOW, free_working_hours=40)
    assert result.urgency == 1 and result.why == 'Overdue'


def test_suggestions_validate_before_capping():
    raw = [None, 'oops', {'type': 'pad_estimates', 'text': None},
           {'type': 'pad_estimates', 'text': 'Use 999 minutes'}]
    raw += [{'type': 'pad_estimates', 'text': f'Use {i} minutes'} for i in range(1, 5)]
    assert [s.text for s in validate_suggestions(raw, dict(a=1, b=2, c=3, d=4))] == [
        'Use 1 minutes', 'Use 2 minutes', 'Use 3 minutes']


def test_analytics_scores_adjacent_hours_without_overlap():
    completed = [CompletedTask('work', 30, 30, hour) for hour in [8] * 5 + [9] * 5 + [16] * 8]
    result = compute_insights(completed=completed, planned_blocks=0, completed_blocks=0,
                             overdue_by_category={}, snoozes_by_category={})
    assert result.focus_windows[0] == (8, 10)
    assert all(a + 2 <= c or a >= d for a, _ in result.focus_windows[:1] for c, d in result.focus_windows[1:])


def test_in_memory_limit_expiry_and_nonpositive_limit(monkeypatch):
    monkeypatch.setattr('app.rate_limit.time.monotonic', lambda: 0)
    limiter = SlidingWindowLimiter()
    assert not limiter.allow(identity='zero', bucket='chat', limit=0)[0]
    assert limiter.allow(identity='old', bucket='chat', limit=1)[0]
    monkeypatch.setattr('app.rate_limit.time.monotonic', lambda: 61)
    assert limiter.allow(identity='new', bucket='chat', limit=1)[0]
    assert ('old', 'chat') not in limiter.events


def test_clerk_seed_ids_are_deterministic_and_scoped():
    first = build_demo('user_alpha', NOW.date())
    assert first == build_demo('user_alpha', NOW.date())
    assert first['tasks'][0]['id'] != build_demo('user_beta', NOW.date())['tasks'][0]['id']
    assert all(row['user_id'] == 'user_alpha' for rows in first.values() for row in rows)


@pytest.mark.parametrize('reply', [LLMResponse('Hello', 'Hello', []),
    LLMResponse('Clarify', 'Clarify', [ToolCall(name='create_task', arguments={'title': 'Task', 'category': 'invalid'})])])
def test_chat_no_action_or_invalid_tool_never_writes(reply):
    session, llm = AsyncMock(), AsyncMock()
    llm.parse.return_value = reply
    result = asyncio.run(handle_chat(session, user_id='user_a', text='Hello', client_tz='UTC', llm=llm))
    assert not result['fallback'] and result['actions'] == []
    session.flush.assert_not_awaited()
    if reply.tool_calls:
        assert result['clarification']


def test_provider_outage_uses_fallback_and_past_date_clarifies(monkeypatch):
    llm, session = AsyncMock(), AsyncMock()
    llm.parse.side_effect = httpx.ReadTimeout('offline')
    result = asyncio.run(handle_chat(session, user_id='user_a', text='Report by yesterday', client_tz='UTC', llm=llm))
    assert result['fallback'] and result['clarification'] and not result['actions']
    session.flush.assert_not_awaited()


def test_configured_anthropic_adapter_sends_tools_and_reads_response(monkeypatch):
    from app import config
    from types import SimpleNamespace
    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(anthropic_api_key='test-key', anthropic_model='test-model'))
    client = configured_llm()
    assert isinstance(client, AnthropicLLMClient)
    real_client = httpx.AsyncClient
    def handler(request):
        import json
        body = json.loads(request.content)
        assert body['model'] == 'test-model'
        assert body['tools'][0]['name'] == 'create_task'
        assert request.headers['x-api-key'] == 'test-key'
        return httpx.Response(200, json={'content': [{'type': 'text', 'text': 'Hello'},
            {'type': 'tool_use', 'id': 't', 'name': 'create_task', 'input': {'title': 'Report'}}]})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(client.parse(text='Create report', context={'timezone': 'UTC'}))
    assert result.reply == 'Hello' and result.tool_calls[0].arguments['title'] == 'Report'
