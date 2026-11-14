"""Visible agent steps: every chat turn reports what LifeOS read, decided and did."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base, Message
from app.services.chat_orchestrator import handle_chat
from app.services.llm_client import LLMResponse, LLMUnavailable
from app.services.nlu_validator import ToolCall

OWNER = 'user_steps'


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


class RecordedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def parse(self, *, text, context, history=None):
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


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


def call(name, **arguments):
    return ToolCall(name=name, arguments=arguments)


def response(reply, *calls):
    return LLMResponse(reply, list(calls), 10, 5, 420, 'test-model')


def summary(steps):
    return [(s['kind'], s['label'], s['status']) for s in steps]


def test_steps_show_context_understanding_each_tool_and_the_capacity_check():
    async def body(session):
        friday = (datetime.now(timezone.utc) + timedelta(days=3)).replace(hour=23, minute=59, second=0, microsecond=0)
        llm = RecordedLLM(response('Added both.',
            call('create_task', title='Finish DBMS report', deadline_iso=friday.isoformat(),
                 deadline_phrase='by ' + friday.strftime('%d %B %Y'), effort_min=120, category='study', confidence='high'),
            call('create_task', title='Call mom', category='social', confidence='low', missing_fields=['when'])))
        result = await handle_chat(session, user_id=OWNER, text='add things', client_tz='UTC', llm=llm)
        await session.commit()
        steps = result['steps']
        assert summary(steps) == [
            ('context', 'Read your workspace', 'done'),
            ('understand', 'Understood your message', 'done'),
            ('tool', 'Create task "Finish DBMS report"', 'done'),
            ('tool', 'Create task "Call mom"', 'asked'),
            ('check', 'Checked your deadlines still fit', 'done'),
        ]
        assert steps[0]['detail'].startswith('0 open tasks, 0 events today')
        assert steps[1]['detail'] == 'Planned 2 steps with test-model' and steps[1]['ms'] == 420
        assert steps[2]['detail'] == 'Finish DBMS report' and steps[2]['tool'] == 'create_task' and 'ms' in steps[2]
        assert 'asked instead of guessing' in steps[3]['detail']
        assert steps[4]['detail'] == 'All deadlines fit'
        stored = (await session.execute(select(Message).where(Message.role == 'assistant'))).scalar_one()
        assert stored.tool_calls['steps'] == steps
    run_with_session(body)


def test_read_only_and_invalid_calls_are_reported_without_a_capacity_check():
    async def body(session):
        llm = RecordedLLM(response('', call('query_schedule', filter='next'), call('create_task', title='')))
        result = await handle_chat(session, user_id=OWNER, text='what next', client_tz='UTC', llm=llm)
        steps = result['steps']
        assert ('tool', 'Create task', 'failed') in summary(steps)
        assert ('tool', 'Check your schedule', 'done') in summary(steps)
        assert next(s for s in steps if s.get('tool') == 'query_schedule')['detail'] == 'Your list is clear.'
        assert all(s['kind'] != 'check' for s in steps)
    run_with_session(body)


def test_confirmation_holds_writes_then_runs_them_on_yes():
    async def body(session):
        titles = ['A', 'B', 'C', 'D']
        llm = RecordedLLM(response('', *[call('create_task', title=t, category='other', confidence='high') for t in titles]))
        held = await handle_chat(session, user_id=OWNER, text='add four', client_tz='UTC', llm=llm)
        await session.commit()
        assert [s['status'] for s in held['steps'] if s['kind'] == 'tool'] == ['waiting'] * 4
        done = await handle_chat(session, user_id=OWNER, text='yes', client_tz='UTC', llm=RecordedLLM())
        await session.commit()
        assert done['steps'][0]['label'] == 'You confirmed the held changes'
        assert [s['status'] for s in done['steps'] if s['kind'] == 'tool'] == ['done'] * 4
    run_with_session(body)


def test_model_outage_reports_the_fallback():
    async def body(session):
        result = await handle_chat(session, user_id=OWNER, text='Buy milk', client_tz='UTC',
                                   llm=RecordedLLM(LLMUnavailable('down')))
        assert result['fallback'] is True
        assert summary(result['steps'])[:2] == [('context', 'Read your workspace', 'done'),
                                                 ('fallback', 'AI model unavailable', 'warning')]
        assert result['steps'][2]['label'] == 'Quick add' and result['steps'][2]['status'] == 'done'
    run_with_session(body)
