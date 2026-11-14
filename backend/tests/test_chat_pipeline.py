"""Chat pipeline with a recorded (fake) LLM: deterministic and free. SQLite backed."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base, Event, Message, PlanBlock, Preference, Reminder, Task
from app.services.chat_orchestrator import handle_chat
from app.services.llm_client import LLMResponse, LLMUnavailable
from app.services.nlu_validator import ToolCall, check_phrase, tool_definitions
from app.services.text_match import reference_score, similarity

OWNER = 'user_chat'


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


class RecordedLLM:
    """Returns queued responses; records the context it was given."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.contexts, self.histories = [], []

    async def parse(self, *, text, context, history=None):
        self.contexts.append(context)
        self.histories.append(history)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def call(name, **arguments):
    return ToolCall(name=name, arguments=arguments)


def run_with_session(body):
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                await body(session)
        finally:
            await engine.dispose()
    asyncio.run(run())


def iso(moment):
    return moment.isoformat()


def test_tool_definitions_cover_every_prd_intent():
    names = {tool['name'] for tool in tool_definitions()}
    assert names == {'create_task', 'update_task', 'complete_task', 'delete_task', 'create_event',
                     'query_schedule', 'plan_day', 'check_capacity', 'set_preference'}
    assert all(tool['input_schema']['type'] == 'object' for tool in tool_definitions())


def test_brain_dump_creates_several_items_with_defaults_and_conflict_check():
    async def body(session):
        now = datetime.now(timezone.utc)
        friday = (now + timedelta(days=3)).replace(hour=23, minute=59, second=0, microsecond=0)
        llm = RecordedLLM(LLMResponse('Added your tasks.', [
            call('create_task', title='Finish DBMS report', deadline_iso=iso(friday), effort_min=180,
                 importance=4, category='study', confidence='high'),
            call('create_task', title='Call mom', category='social', confidence='high'),
            call('create_event', title='Dentist', start_iso=iso(now + timedelta(days=1)), duration_min=45),
        ]))
        result = await handle_chat(session, user_id=OWNER, text='brain dump', client_tz='UTC', llm=llm)
        await session.commit()
        assert [a['type'] for a in result['actions']] == ['task_created', 'task_created', 'event_created']
        report = result['actions'][0]['task']
        assert report['effort_est_min'] == 180 and report['importance'] == 4 and report['why']
        assert result['actions'][0]['task']['deadline_label'].startswith(friday.strftime('%a'))
        assert result['actions'][1]['task']['effort_est_min'] == 30  # social category default
        assert all(a['undo_until'] for a in result['actions'])
        assert result['message_id'] and 'spoken_reply' not in result
        assert len((await session.execute(select(Event))).scalars().all()) == 1
        roles = [m.role for m in (await session.execute(select(Message).order_by(Message.created_at))).scalars()]
        assert roles == ['user', 'assistant']
        # Undo on the first card still works although later items re-scored it.
        from uuid import UUID
        from app.services.domain_service import undo_logged_action
        await undo_logged_action(session, OWNER, UUID(result['actions'][0]['action_id']))
        await session.commit()
        titles = [t.title for t in (await session.execute(select(Task))).scalars()]
        assert 'Finish DBMS report' not in titles and 'Call mom' in titles
    run_with_session(body)


def test_reference_resolution_update_pronoun_and_ambiguity():
    async def body(session):
        now = datetime.now(timezone.utc)
        llm = RecordedLLM(
            LLMResponse('', [call('create_task', title='Finish DBMS report', category='study'),
                             call('create_task', title='Buy groceries', category='errand')]),
            LLMResponse('', [call('update_task', task_ref='the report', effort_min=240)]),
            LLMResponse('', [call('update_task', task_ref='it', importance=5)]),
            LLMResponse('', [call('update_task', task_id='00000000-0000-4000-8000-000000000000', task_ref='spaceship', importance=2)]),
        )
        await handle_chat(session, user_id=OWNER, text='add', client_tz='UTC', llm=llm)
        await session.commit()
        result = await handle_chat(session, user_id=OWNER, text='make the report 4 hours', client_tz='UTC', llm=llm)
        await session.commit()
        assert result['actions'][0]['type'] == 'task_updated'
        assert result['actions'][0]['task']['effort_est_min'] == 240
        report_id = result['actions'][0]['task_id']
        result = await handle_chat(session, user_id=OWNER, text='make it urgent', client_tz='UTC', llm=llm)
        await session.commit()
        # "it" resolves to the last touched item, carried over from the previous turn.
        assert llm.contexts[2]['last_touched_item_id'] == report_id
        assert result['actions'][0]['task_id'] == report_id
        assert result['actions'][0]['task']['importance'] == 5
        assert result['actions'][0]['task']['title'] == 'Finish DBMS report'
        # A hallucinated id falls back to the reference, which matches nothing: ask.
        result = await handle_chat(session, user_id=OWNER, text='?', client_tz='UTC', llm=llm)
        assert not result['actions'] and result['clarification']['question']
        # History reaches the LLM (working memory).
        assert llm.histories[-1] and llm.histories[-1][0]['role'] == 'user'
    run_with_session(body)


def test_two_close_matches_ask_which_one():
    async def body(session):
        session.add_all([Task(user_id=OWNER, title='ML quiz study', created_at=datetime.now(timezone.utc)),
                         Task(user_id=OWNER, title='ML quiz notes', created_at=datetime.now(timezone.utc))])
        await session.commit()
        llm = RecordedLLM(LLMResponse('', [call('complete_task', task_ref='ML quiz')]))
        result = await handle_chat(session, user_id=OWNER, text='done with the ML quiz', client_tz='UTC', llm=llm)
        assert not result['actions']
        assert result['clarification']['question'].startswith('Which one')
        assert len(result['clarification']['options']) == 2
    run_with_session(body)


def test_delete_needs_confirmation_then_yes_executes_and_no_cancels():
    async def body(session):
        session.add(Task(user_id=OWNER, title='Dentist booking', created_at=datetime.now(timezone.utc)))
        session.add(Task(user_id=OWNER, title='Gym bag', created_at=datetime.now(timezone.utc)))
        await session.commit()
        llm = RecordedLLM(LLMResponse('', [call('delete_task', task_ref='dentist')]),
                          LLMResponse('', [call('delete_task', task_ref='gym bag')]))
        first = await handle_chat(session, user_id=OWNER, text='cancel the dentist', client_tz='UTC', llm=llm)
        await session.commit()
        assert not first['actions'] and first['confirmation']['options'] == ['Yes', 'No']
        assert (await session.execute(select(Task).where(Task.title == 'Dentist booking'))).scalar_one().status == 'open'
        second = await handle_chat(session, user_id=OWNER, text='yes', client_tz='UTC', llm=llm)
        await session.commit()
        assert second['actions'][0]['type'] == 'task_deleted' and second['actions'][0]['batch_id']
        assert (await session.execute(select(Task).where(Task.title == 'Dentist booking'))).scalar_one().status == 'dropped'
        await handle_chat(session, user_id=OWNER, text='delete gym bag', client_tz='UTC', llm=llm)
        await session.commit()
        cancelled = await handle_chat(session, user_id=OWNER, text='no', client_tz='UTC', llm=llm)
        assert not cancelled['actions']
        assert (await session.execute(select(Task).where(Task.title == 'Gym bag'))).scalar_one().status == 'open'
    run_with_session(body)


def test_more_than_three_writes_require_confirmation():
    async def body(session):
        calls = [call('create_task', title=f'Item {n}', category='other') for n in range(4)]
        result = await handle_chat(session, user_id=OWNER, text='four things', client_tz='UTC',
                                   llm=RecordedLLM(LLMResponse('', calls)))
        assert result['confirmation'] and not result['actions']
        assert not (await session.execute(select(Task))).scalars().all()
    run_with_session(body)


def test_duplicate_guard_offers_instead_of_creating():
    async def body(session):
        deadline = datetime.now(timezone.utc) + timedelta(days=2)
        session.add(Task(user_id=OWNER, title='Pay rent', deadline_at=deadline, created_at=datetime.now(timezone.utc)))
        await session.commit()
        llm = RecordedLLM(LLMResponse('', [call('create_task', title='Pay rent', category='finance',
                                                deadline_iso=iso(deadline + timedelta(hours=3)))]))
        result = await handle_chat(session, user_id=OWNER, text='pay rent', client_tz='UTC', llm=llm)
        assert not result['actions'] and 'already have' in result['confirmation']['prompt']
        assert len((await session.execute(select(Task))).scalars().all()) == 1
    run_with_session(body)


def test_custom_reminder_overrides_rules():
    async def body(session):
        now = datetime.now(timezone.utc)
        llm = RecordedLLM(LLMResponse('', [call('create_task', title='Start report', category='study',
            deadline_iso=iso(now + timedelta(days=2)), remind_at_iso=iso(now + timedelta(minutes=1)))]))
        result = await handle_chat(session, user_id=OWNER, text='remind me', client_tz='UTC', llm=llm)
        pending = (await session.execute(select(Reminder).where(Reminder.status == 'pending'))).scalars().all()
        assert [r.kind for r in pending] == ['custom']
        assert result['actions'][0]['type'] == 'task_created'
    run_with_session(body)


def test_set_preference_merges_and_query_and_plan_day_answer_from_code():
    async def body(session):
        session.add(Preference(user_id=OWNER, key='work_hours', value={'start': '00:00', 'end': '23:59'}))
        now = datetime.now(timezone.utc)
        session.add(Task(user_id=OWNER, title='Essay', deadline_at=now + timedelta(days=1), effort_est_min=60,
                         created_at=now))
        await session.commit()
        llm = RecordedLLM(
            LLMResponse('Noted.', [call('set_preference', key='work_hours', value={'end': '21:00'})]),
            LLMResponse('', [call('query_schedule', filter='due')]),
            LLMResponse('', [call('plan_day', not_after='23:00')]),
            LLMResponse('', [call('check_capacity', title='Six hour job', effort_min=360,
                                  deadline_iso=iso(now + timedelta(hours=2)))]),
        )
        await handle_chat(session, user_id=OWNER, text='I never work after 9 pm', client_tz='UTC', llm=llm)
        await session.commit()
        pref = (await session.execute(select(Preference).where(Preference.key == 'work_hours'))).scalar_one()
        assert pref.value == {'start': '00:00', 'end': '21:00'} and pref.source == 'stated'
        due = await handle_chat(session, user_id=OWNER, text="what's due", client_tz='UTC', llm=llm)
        assert due['actions'][0]['type'] == 'schedule' and 'Essay' in due['reply']
        plan = await handle_chat(session, user_id=OWNER, text='plan my day', client_tz='UTC', llm=llm)
        await session.commit()
        assert plan['actions'][0]['type'] == 'plan_generated'
        assert (await session.execute(select(PlanBlock))).scalars().all() or plan['actions'][0]['unplaced_task_ids']
        before = len((await session.execute(select(Task))).scalars().all())
        capacity = await handle_chat(session, user_id=OWNER, text='can I take it', client_tz='UTC', llm=llm)
        assert capacity['actions'][0]['type'] == 'capacity_check'
        assert capacity['actions'][0]['result']['fits'] is False
        assert len((await session.execute(select(Task))).scalars().all()) == before  # hypothetical only
    run_with_session(body)


def test_llm_outage_falls_back_to_quick_add():
    async def body(session):
        llm = RecordedLLM(LLMUnavailable('timeout'))
        result = await handle_chat(session, user_id=OWNER, text='Buy milk by tomorrow', client_tz='UTC', llm=llm)
        assert result['fallback'] and result['actions'][0]['title'] == 'Buy milk'
    run_with_session(body)


def test_out_of_scope_message_writes_nothing():
    async def body(session):
        result = await handle_chat(session, user_id=OWNER, text='tell me a joke', client_tz='UTC',
                                   llm=RecordedLLM(LLMResponse('I plan, I do not joke. What is on your plate?', [])))
        assert result['actions'] == [] and result['reply'].startswith('I plan')
        assert not (await session.execute(select(Task))).scalars().all()
    run_with_session(body)


@pytest.mark.parametrize('phrase,offset_days,expected_ok', [
    ('by Friday', 0, True), ('Friday evening', 0, True), ('by Friday', 7, False)])
def test_date_only_phrases_compare_calendar_dates(phrase, offset_days, expected_ok):
    now = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)  # Monday
    friday = datetime(2026, 11, 20, 23, 59, tzinfo=timezone.utc) + timedelta(days=offset_days)
    assert (check_phrase(friday, phrase, now=now, timezone='UTC') is None) is expected_ok


def test_trigram_reference_scores():
    assert similarity('report', 'report') == 1
    assert reference_score('the report', 'Finish DBMS report') >= 0.6
    assert reference_score('groceries', 'Finish DBMS report') < 0.3
