"""Morning brief: fixed-template numbers, nudges with one action, safe translation and the morning push."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base, Conflict, Reminder, Task
from app.services import brief_service as bs

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)  # Monday 08:00 UTC
UTC = ZoneInfo('UTC')


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


def task(title, deadline=None, status='open'):
    return SimpleNamespace(id=uuid4(), title=title, deadline_at=deadline, status=status)


def data(**values):
    base = dict(now=NOW, zone=UTC, due_today=[], overdue=[], soon_unplanned=[], open_count=0,
                blocks_today=[], events_today=[], conflicts=[], titles={})
    return bs.BriefData(**{**base, **values})


def test_empty_list_gets_a_calm_brief_and_no_nudges():
    brief = bs.compose(data(), name='Asha')
    assert brief['headline'] == "Good morning, Asha. Your list is clear. Tell me what's on your mind."
    assert brief['nudges'] == [] and brief['lines'] == []


def test_risks_come_first_with_one_action_each():
    report = task('DBMS report', NOW + timedelta(days=4))
    late = task('Pay rent', NOW - timedelta(days=1))
    soon = task('Lab 3', NOW + timedelta(hours=30))
    conflict = SimpleNamespace(id=uuid4(), needed_min=600, free_min=480, deadline_at=NOW + timedelta(days=4),
                               task_ids=[str(report.id)])
    block = SimpleNamespace(task_id=report.id, start_at=NOW + timedelta(hours=2), end_at=NOW + timedelta(hours=3, minutes=30))
    brief = bs.compose(data(overdue=[late], soon_unplanned=[soon], open_count=3, blocks_today=[block],
                            conflicts=[conflict], titles={str(t.id): t.title for t in (report, late, soon)}))
    assert brief['headline'] == 'Good morning. 1 deadline is at risk, and I have a fix ready.'
    assert "Heads up: you're 2 h short before Fri 20 Nov 08:00." in brief['lines']
    assert '1 focus block planned (1 h 30 min); next is DBMS report at 10:00.' in brief['lines']
    kinds = [n['kind'] for n in brief['nudges']]
    assert kinds == ['conflict', 'overdue', 'unplanned']
    assert brief['nudges'][0]['action'] == {'type': 'open_conflict', 'conflict_id': str(conflict.id), 'label': 'See fixes'}
    assert brief['nudges'][1]['action']['deadline_at'] == '2026-11-17T23:59:00+00:00'
    assert brief['nudges'][2]['action']['type'] == 'plan'
    assert brief['counts'] == {'due_today': 0, 'overdue': 1, 'at_risk': 1, 'focus_min': 90, 'events': 0}
    assert len(brief['spoken']) <= 500 and brief['spoken'].startswith(brief['headline'])


def test_unplanned_day_suggests_planning_until_evening():
    assert bs.compose(data(open_count=2))['nudges'][0]['kind'] == 'plan'
    late = bs.compose(data(open_count=2, now=NOW.replace(hour=21)))
    assert late['nudges'] == [] and late['headline'].startswith('Good evening')


class Writer:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def write(self, *, system, payload):
        self.calls.append((system, payload))
        return self.reply if isinstance(self.reply, str) else self.reply(payload)


def brief_with_risk():
    late = task('Pay rent', NOW - timedelta(days=1))
    return bs.compose(data(overdue=[late], open_count=1, titles={str(late.id): late.title}))


def test_translation_is_used_only_when_numbers_survive():
    brief = brief_with_risk()

    def hindi(payload):
        return json.dumps(ensure_ascii=False, obj={'headline': 'सुप्रभात। पहले 1 बकाया काम निपटाएँ।', 'lines': ['1 काम बकाया है।'],
                           'spoken': 'सुप्रभात। पहले 1 बकाया काम निपटाएँ। 1 काम बकाया है।',
                           'nudges': [{'title': 'Pay rent बकाया है', 'detail': 'यह Sun 15 Nov 08:00 को था। कल पर ले जाएँ।', 'label': 'कल पर ले जाएँ'},
                                      {'title': 'आज के लिए कुछ तय नहीं है', 'detail': 'आपके 1 काम खुले हैं।', 'label': 'मेरा दिन प्लान करें'}]})

    out = asyncio.run(bs.translate(brief, 'hi', Writer(hindi)))
    assert out['translated'] is True and out['language'] == 'hi'
    assert out['nudges'][0]['action']['label'] == 'कल पर ले जाएँ'
    assert out['nudges'][0]['action']['task_id'] == brief['nudges'][0]['action']['task_id']

    def changed_number(payload):
        return hindi(payload).replace('1 काम', '2 काम')
    assert asyncio.run(bs.translate(brief, 'hi', Writer(changed_number)))['translated'] is False
    assert asyncio.run(bs.translate(brief, 'hi', Writer('not json')))['translated'] is False
    assert asyncio.run(bs.translate(brief, 'en-GB', Writer(hindi)))['translated'] is False


def test_push_message_carries_the_risk():
    conflict = SimpleNamespace(id=uuid4(), needed_min=300, free_min=120, deadline_at=NOW + timedelta(days=1), task_ids=[])
    brief = bs.compose(data(conflicts=[conflict], open_count=1))
    assert bs.push_message(brief) == ("Good morning. 1 deadline is at risk, and I have a fix ready. "
                                      "Heads up: you're 3 h short before tomorrow 08:00.")


def test_morning_push_is_sent_for_risk_even_without_blocks():
    from app import worker

    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session, session.begin():
                session.add(Task(user_id='user_brief', title='Overdue essay', deadline_at=NOW - timedelta(days=2),
                                 effort_est_min=30, importance=3, category='study', created_at=NOW - timedelta(days=5)))
            async with factory() as session, session.begin():
                sent = await worker.plan_today(session, 'user_brief', now=NOW.replace(hour=10))
            async with factory() as session:
                reminders = (await session.execute(select(Reminder).where(Reminder.kind == 'daily_plan'))).scalars().all()
        finally:
            await engine.dispose()
        return sent, reminders
    sent, reminders = asyncio.run(run())
    assert sent is True and len(reminders) == 1
    assert 'overdue' in reminders[0].message
