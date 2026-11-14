"""Syllabus import: extraction normalisation, offline fallback, PDF reading, batch save and undo."""
import asyncio
import base64
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import ActionLog, Base, PlanBlock, Task
from app.schemas import TaskCreate
from app.services import syllabus_import as si
from app.services.llm_client import FallbackLLMClient, GroqLLMClient

OWNER = 'user_import'
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
UTC = ZoneInfo('UTC')


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


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


def item(**values):
    base = {'title': 'Submit Lab 3', 'kind': 'lab', 'due_date': '2026-11-20', 'due_time': None,
            'effort_min': None, 'importance': None, 'source_quote': 'Lab 3 due Nov 20'}
    return {**base, **values}


def test_normalise_defaults_dedupes_skips_past_and_sorts():
    raw = {'course': 'CS101', 'items': [
        item(title='Prepare for Midterm', kind='exam', due_date='2026-12-01', source_quote='Midterm Dec 1'),
        item(),
        item(),  # duplicate
        item(title='Old quiz', kind='quiz', due_date='2026-10-01'),  # past
        item(title='', kind='lab'),  # invalid
        item(title='Read chapter 4', kind='reading', due_date=None),
        item(title='Final project', kind='project', due_date='2026-11-18', due_time='17:30', effort_min=9999, importance=9),
        'nonsense',
    ]}
    result = si.normalise(raw, now=NOW, zone=UTC)
    titles = [p['title'] for p in result['proposals']]
    assert titles == ['Final project', 'Submit Lab 3', 'Prepare for Midterm', 'Read chapter 4']
    assert result['skipped_past'] == 1 and result['skipped_invalid'] == 2 and result['course'] == 'CS101'
    project, lab, exam, reading = result['proposals']
    assert project['deadline_at'] == '2026-11-18T17:30:00+00:00'
    assert project['effort_est_min'] == 600 and project['importance'] == 5  # clamped
    assert lab['deadline_at'].endswith('23:59:00+00:00') and lab['effort_est_min'] == 120
    assert exam['deadline_at'] == '2026-12-01T09:00:00+00:00' and exam['importance'] == 5
    assert reading['deadline_at'] is None
    assert lab['notes'] == 'From syllabus: "Lab 3 due Nov 20"' and lab['category'] == 'study'
    # Every proposal is a valid task payload.
    assert all(TaskCreate(**{k: v for k, v in p.items() if k != 'kind'}) for p in result['proposals'])


def test_normalise_uses_the_user_time_zone():
    result = si.normalise({'items': [item(due_time='10:00')]}, now=NOW, zone=ZoneInfo('Asia/Kolkata'))
    assert result['proposals'][0]['deadline_at'] == '2026-11-20T04:30:00+00:00'


def test_heuristic_fallback_finds_dated_deliverables():
    text = '\n'.join(['CS101 Syllabus', 'Office hours: Monday 3pm', 'Assignment 1 due November 20, 2026',
                      'Midterm exam: December 3, 2026 at 10:00', 'Lecture notes are online',
                      'Quiz 1 (Sept 12)', 'HW 4 due Dec 5 11:59pm'])
    result = asyncio.run(si.propose(FallbackLLMClient(), text, now=NOW, tz_name='UTC'))
    assert result['fallback'] is True
    by_kind = {p['kind']: p for p in result['proposals']}
    assert set(by_kind) == {'assignment', 'exam'}
    assert [p['deadline_at'][:10] for p in result['proposals'] if p['kind'] == 'assignment'] == ['2026-11-20', '2026-12-05']
    assert result['skipped_past'] == 1  # Sept 12 without a year is this term's past quiz, not next year's
    assert by_kind['exam']['deadline_at'] == '2026-12-03T10:00:00+00:00'


def test_llm_extraction_uses_forced_tool_call(monkeypatch):
    client = GroqLLMClient('test-only-key', 'test-model')
    seen = {}

    async def respond(body):
        seen.update(body)
        return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'propose_tasks',
            'arguments': '{"course":"Bio","items":[{"title":"Essay","kind":"assignment","due_date":"2026-11-25",'
                         '"due_time":null,"effort_min":120,"importance":4,"source_quote":"Essay due 11/25"}]}'}}]}}]}

    monkeypatch.setattr(client, '_post', respond)
    result = asyncio.run(si.propose(client, 'Essay due 11/25', now=NOW, tz_name='UTC'))
    assert result['fallback'] is False and result['course'] == 'Bio'
    assert result['proposals'][0]['title'] == 'Essay' and result['proposals'][0]['effort_est_min'] == 120
    assert seen['tool_choice'] == {'type': 'function', 'function': {'name': 'propose_tasks'}}
    assert 'untrusted data' in seen['messages'][0]['content']


def test_malformed_llm_output_falls_back(monkeypatch):
    client = GroqLLMClient('test-only-key', 'test-model')

    async def respond(body):
        return {'choices': [{'message': {'content': 'no tools'}}]}

    monkeypatch.setattr(client, '_post', respond)
    result = asyncio.run(si.propose(client, 'Quiz 2 on November 30, 2026', now=NOW, tz_name='UTC'))
    assert result['fallback'] is True and result['proposals'][0]['kind'] == 'quiz'


def test_read_source_validates_input():
    with pytest.raises(si.ImportInputError, match='Paste your syllabus'):
        si.read_source('  ', None)
    with pytest.raises(si.ImportInputError, match='could not be read'):
        si.read_source(None, '***')
    with pytest.raises(si.ImportInputError, match='not a PDF'):
        si.read_source(None, base64.b64encode(b'hello').decode())
    assert si.read_source(' Exam Dec 1 ', None) == 'Exam Dec 1'


def test_pdf_text_is_extracted():
    pypdf = pytest.importorskip('pypdf')
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    # A blank page has no text: the user is told to paste instead.
    with pytest.raises(si.ImportInputError, match='No text was found'):
        si.read_source(None, base64.b64encode(buffer.getvalue()).decode())


def test_save_creates_one_batch_plans_and_undoes():
    async def body(session):
        soon = datetime.now(timezone.utc) + timedelta(days=3)
        tasks = [TaskCreate(title='Submit essay', deadline_at=soon, effort_est_min=60, category='study'),
                 TaskCreate(title='Prepare for quiz', deadline_at=soon + timedelta(days=1), effort_est_min=90, category='study')]
        result = await si.save_proposals(session, OWNER, tasks, plan=True)
        await session.commit()
        assert len(result['task_ids']) == 2 and result['planned'] is True
        logs = (await session.execute(select(ActionLog).where(ActionLog.batch_id == UUID(result['batch_id'])))).scalars().all()
        assert len(logs) == 2
        assert (await session.execute(select(PlanBlock))).scalars().all(), 'the plan should schedule the new work'
        undone = await si.undo_import(session, OWNER, UUID(result['batch_id']))
        await session.commit()
        assert undone == {'undone': True, 'count': 2}
        assert (await session.execute(select(Task))).scalars().all() == []
        assert (await session.execute(select(PlanBlock))).scalars().all() == []
    run_with_session(body)
