"""ICS calendar import: parsing, time zones, recurrence safety, dedupe and undo."""
import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.api.ics_import import EventProposal, SaveRequest
from app.models import Base, Event
from app.services import ics_import as ics

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
OWNER = 'user_ics'


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


def cal(*events):
    return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n' + ''.join(f'BEGIN:VEVENT\r\n{e}\r\nEND:VEVENT\r\n' for e in events) + 'END:VCALENDAR\r\n'


def parse(*events, tz='UTC'):
    return ics.parse_calendar(cal(*events), tz, NOW)


def test_utc_timed_event_with_escapes_and_folding():
    result = parse('UID:a1\r\nSUMMARY:Sync\\, weekly\r\nDTSTART:20261120T100000Z\r\nDTEND:20261120T110000Z\r\nLOCATION:Room\r\n  4')
    item = result['proposals'][0]
    assert item['title'] == 'Sync, weekly'
    assert item['location'] == 'Room 4'
    assert item['start_at'] == '2026-11-20T10:00:00+00:00'
    assert item['external_id'] == 'a1'


def test_tzid_and_floating_times_convert_to_utc():
    result = parse('UID:t\r\nSUMMARY:Class\r\nDTSTART;TZID=America/New_York:20261120T090000\r\nDTEND;TZID=America/New_York:20261120T100000',
                   'UID:f\r\nSUMMARY:Floating\r\nDTSTART:20261121T090000\r\nDTEND:20261121T100000', tz='Asia/Kolkata')
    by_id = {p['external_id']: p for p in result['proposals']}
    assert by_id['t']['start_at'] == '2026-11-20T14:00:00+00:00'
    assert by_id['f']['start_at'] == '2026-11-21T03:30:00+00:00'  # 09:00 in the user's zone


def test_all_day_and_duration():
    result = parse('UID:d\r\nSUMMARY:Holiday\r\nDTSTART;VALUE=DATE:20261125\r\nDTEND;VALUE=DATE:20261126',
                   'UID:e\r\nSUMMARY:Lab\r\nDTSTART:20261122T090000Z\r\nDURATION:PT1H30M')
    by_id = {p['external_id']: p for p in result['proposals']}
    assert by_id['d']['all_day'] and by_id['d']['end_at'] == '2026-11-26T00:00:00+00:00'
    assert by_id['e']['end_at'] == '2026-11-22T10:30:00+00:00'


def test_skips_past_cancelled_invalid_and_duplicates():
    result = parse('UID:p\r\nSUMMARY:Old\r\nDTSTART:20200101T100000Z\r\nDTEND:20200101T110000Z',
                   'UID:c\r\nSUMMARY:Gone\r\nSTATUS:CANCELLED\r\nDTSTART:20261120T100000Z\r\nDTEND:20261120T110000Z',
                   'UID:i\r\nSUMMARY:Bad\r\nDTSTART:garbage',
                   'UID:z\r\nSUMMARY:Backwards\r\nDTSTART:20261120T110000Z\r\nDTEND:20261120T100000Z',
                   'UID:k\r\nSUMMARY:Keep\r\nDTSTART:20261120T100000Z\r\nDTEND:20261120T110000Z',
                   'UID:k\r\nSUMMARY:Keep\r\nDTSTART:20261120T100000Z\r\nDTEND:20261120T110000Z')
    assert [p['external_id'] for p in result['proposals']] == ['k']
    assert (result['skipped_past'], result['skipped_cancelled'], result['skipped_invalid'], result['skipped_duplicate']) == (1, 1, 2, 1)


def test_recurrence_kept_when_valid_and_date_until_fixed():
    result = parse('UID:r\r\nSUMMARY:Standup\r\nDTSTART:20261116T090000Z\r\nDTEND:20261116T091500Z\r\nRRULE:FREQ=WEEKLY;BYDAY=MO;UNTIL=20261231')
    rule = result['proposals'][0]['rrule']
    assert 'UNTIL=20261231T235959Z' in rule


def test_exdate_removes_a_skipped_occurrence_from_the_rule():
    from dateutil.rrule import rrulestr
    result = parse('UID:x\r\nSUMMARY:Standup\r\nDTSTART:20261116T090000Z\r\nDTEND:20261116T091500Z\r\nRRULE:FREQ=WEEKLY;COUNT=3\r\nEXDATE:20261123T090000Z')
    rule = result['proposals'][0]['rrule']
    start = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)
    days = [d.day for d in rrulestr(rule, dtstart=start)]
    assert days == [16, 30]


def test_recurrence_ended_in_past_or_broken_is_skipped():
    result = parse('UID:o\r\nSUMMARY:Ended\r\nDTSTART:20200106T090000Z\r\nDTEND:20200106T100000Z\r\nRRULE:FREQ=WEEKLY;UNTIL=20200301T000000Z',
                   'UID:b\r\nSUMMARY:Broken\r\nDTSTART:20261116T090000Z\r\nDTEND:20261116T100000Z\r\nRRULE:FREQ=NONSENSE')
    assert result['proposals'] == []
    assert result['skipped_past'] == 1 and result['skipped_invalid'] == 1


def test_alarm_properties_are_ignored_and_source_validated():
    result = parse('UID:v\r\nSUMMARY:Real\r\nDTSTART:20261120T100000Z\r\nDTEND:20261120T110000Z\r\nBEGIN:VALARM\r\nSUMMARY:Alarm\r\nEND:VALARM')
    assert result['proposals'][0]['title'] == 'Real'
    with pytest.raises(ics.IcsInputError):
        ics.read_source('hello')
    with pytest.raises(ics.IcsInputError):
        ics.read_source('   ')


def test_save_dedupes_and_undo():
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                parsed = parse('UID:s1\r\nSUMMARY:One\r\nDTSTART:20261120T100000Z\r\nDTEND:20261120T110000Z')
                items = SaveRequest(events=[EventProposal(**p) for p in parsed['proposals']]).events
                first = await ics.save_events(session, OWNER, items)
                again = await ics.save_events(session, OWNER, items)
                assert (first['created'], again['created'], again['skipped_existing']) == (1, 0, 1)
                row = (await session.execute(select(Event))).scalar_one()
                assert row.source == 'ics' and row.external_id == 's1'
                undone = await ics.undo_import(session, OWNER, __import__('uuid').UUID(first['batch_id']))
                assert undone['count'] == 1
                assert (await session.execute(select(Event.cancelled))).scalar_one() is True
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_http_parse_save_undo_roundtrip():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.ics_import import router
    from app.auth import current_user_id
    from app.db import get_session

    async def setup():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        return engine, async_sessionmaker(engine, expire_on_commit=False)

    loop = asyncio.new_event_loop()
    engine, factory = loop.run_until_complete(setup())
    app = FastAPI()
    app.include_router(router)

    async def session_dep():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = session_dep
    app.dependency_overrides[current_user_id] = lambda: OWNER
    text = cal('UID:h1\r\nSUMMARY:Exam\r\nDTSTART:20271120T100000Z\r\nDTEND:20271120T110000Z')
    with TestClient(app) as client:
        parsed = client.post('/api/import/calendar/parse', json={'text': text, 'client_tz': 'UTC'})
        assert parsed.status_code == 200, parsed.text
        events = parsed.json()['proposals']
        assert events[0]['title'] == 'Exam'
        assert client.post('/api/import/calendar/parse', json={'text': 'nope'}).status_code == 422
        saved = client.post('/api/import/calendar/save', json={'events': events})
        assert saved.status_code == 200 and saved.json()['created'] == 1, saved.text
        again = client.post('/api/import/calendar/save', json={'events': events})
        assert again.json()['created'] == 0
        undone = client.post(f"/api/import/calendar/{saved.json()['batch_id']}/undo")
        assert undone.status_code == 200 and undone.json()['count'] == 1
    loop.run_until_complete(engine.dispose())
