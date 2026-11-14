"""Insights, Capacity Guard resolution, reschedule, worker delivery, privacy APIs, CORS."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import (ActionLog, ActivityEvent, Base, Conflict, Message, Preference, PushSubscription, Reminder,
                        Routine, Suggestion, Task, User, WorkerStatus)

OWNER = 'user_enhanced'


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


def with_factory(body):
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            await body(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    asyncio.run(run())


async def seed_priya(factory, anchor: date):
    from seed_demo import build_demo
    from app import models
    rows = build_demo(OWNER, anchor, 'UTC')
    tables = {'tasks': models.Task, 'events': models.Event, 'preferences': models.Preference,
              'routines': models.Routine, 'plan_blocks': models.PlanBlock,
              'activity_events': models.ActivityEvent, 'reminders': models.Reminder}
    async with factory() as session:
        for name, model in tables.items():
            for values in rows[name]:
                session.add(model(**values))
            await session.flush()
        await session.commit()


def test_insights_from_seeded_history_match_hand_calculation():
    async def body(factory):
        from app.services.insight_service import compute_user_insights, generate_suggestions, latest_suggestions
        now = datetime.now(timezone.utc)
        await seed_priya(factory, now.date())
        async with factory() as session:
            data = await compute_user_insights(session, OWNER, now=now)
            # 28 seeded completions: study takes exactly 1.6x, errands 1.0x.
            assert data['calibration_factors'] == {'study': 1.6, 'errand': 1.0}
            assert data['cold_start'] is False and data['samples'] == 28
            assert data['plan_adherence'] == 1.0 and data['completed_14d'] >= 26
            assert len(data['completion_chart']) == 14
            assert data['focus_windows'] and data['focus_windows'][0][1] - data['focus_windows'][0][0] == 2
            suggestions = await generate_suggestions(data)
            assert suggestions[0]['type'] == 'pad_estimates' and '1.6' in suggestions[0]['text']
            rows = await latest_suggestions(session, OWNER, data, now=now)
            again = await latest_suggestions(session, OWNER, data, now=now)
            assert [r.id for r in rows] == [r.id for r in again]  # generated once per day
    with_factory(body)


def test_llm_suggestion_with_invented_number_is_rejected():
    from app.services.insight_service import generate_suggestions

    class Writer:
        async def write(self, *, system, payload):
            return '{"suggestions":[{"type":"pad_estimates","text":"Study takes 2.4x longer."}]}'
    insights = {'calibration_factors': {'study': 1.6}, 'snooze_rates': {}, 'overdue_rates': {},
                'focus_windows': [], 'plan_adherence': 0.5, 'completed_14d': 10, 'samples': 12}
    result = asyncio.run(generate_suggestions(insights, Writer()))
    assert result and '1.6' in result[0]['text'] and '2.4' not in result[0]['text']


def test_apply_suggestion_sets_preference():
    async def body(factory):
        from app.services.insight_service import apply_suggestion
        async with factory() as session:
            row = Suggestion(user_id=OWNER, type='move_focus_window', text='Protect mornings',
                             payload={'windows': [['08:00', '10:00']]})
            session.add(row)
            await session.flush()
            result = await apply_suggestion(session, OWNER, row)
            await session.commit()
            pref = (await session.execute(select(Preference).where(Preference.key == 'focus_windows'))).scalar_one()
            assert pref.value == {'windows': [['08:00', '10:00']]} and result['status'] == 'applied'
    with_factory(body)


def overloaded(session, now):
    session.add_all([
        Preference(user_id=OWNER, key='timezone', value={'name': 'UTC'}),
        Preference(user_id=OWNER, key='work_hours', value={'start': '09:00', 'end': '12:00'}),
        Preference(user_id=OWNER, key='estimate_padding', value={'enabled': False}),
    ])
    deadline = (now + timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
    session.add_all([Task(user_id=OWNER, title='Report', deadline_at=deadline, effort_est_min=300, importance=5, created_at=now),
                     Task(user_id=OWNER, title='Quiz prep', deadline_at=deadline, effort_est_min=240, importance=2, created_at=now)])
    return deadline


def test_capacity_guard_detects_simulates_and_resolves_with_batch_undo():
    async def body(factory):
        from app.services.conflict_service import resolve, simulate_options
        from app.services.planning_service import detect_conflicts
        from app.api.actions import undo_batch
        now = datetime.now(timezone.utc)
        async with factory() as session:
            overloaded(session, now)
            await session.commit()
            conflicts = await detect_conflicts(session, OWNER, now=now)
            await session.commit()
            assert len(conflicts) == 1 and conflicts[0].needed_min == 540
            conflict = conflicts[0]
            options = await simulate_options(session, OWNER, conflict, now=now)
            types = [item['type'] for item in options]
            assert types == ['extend_hours', 'move_flexible', 'renegotiate']
            assert all('preview' in item for item in options)
            assert 'draft_message' in options[2]
            assert len((await session.execute(select(Conflict))).scalars().all()) == 1  # simulation wrote nothing
            result = await resolve(session, OWNER, conflict, 'move_flexible', now=now)
            await session.commit()
            quiz = (await session.execute(select(Task).where(Task.title == 'Quiz prep'))).scalar_one()
            assert quiz.deadline_at.replace(tzinfo=timezone.utc) > conflict.deadline_at.replace(tzinfo=timezone.utc)
            assert result['status'] == 'resolved' and result['batch_id']
            await undo_batch(UUID(result['batch_id']), session, OWNER)
            quiz = (await session.execute(select(Task).where(Task.title == 'Quiz prep'))).scalar_one()
            assert quiz.deadline_at.replace(tzinfo=timezone.utc) == conflict.deadline_at.replace(tzinfo=timezone.utc)
    with_factory(body)


def test_extend_hours_option_writes_dated_override():
    async def body(factory):
        from app.services.conflict_service import resolve
        from app.services.planning_service import detect_conflicts
        now = datetime.now(timezone.utc)
        async with factory() as session:
            overloaded(session, now)
            await session.commit()
            conflict = (await detect_conflicts(session, OWNER, now=now))[0]
            await resolve(session, OWNER, conflict, 'extend_hours', now=now)
            await session.commit()
            pref = (await session.execute(select(Preference).where(Preference.key == 'work_hours_overrides'))).scalar_one()
            assert pref.value['dates'] and all(v['end'] == '21:00' for v in pref.value['dates'].values())
    with_factory(body)


def test_reschedule_offers_three_slots_and_moves_reminder():
    async def body(factory):
        from app.api.reminder_actions import RescheduleRequest, reminder_action, reschedule
        from app.schemas_reminders import ReminderActionRequest
        now = datetime.now(timezone.utc)
        async with factory() as session:
            session.add(Preference(user_id=OWNER, key='work_hours', value={'start': '00:00', 'end': '23:59'}))
            task = Task(user_id=OWNER, title='Report', deadline_at=now + timedelta(days=3), effort_est_min=60, created_at=now)
            session.add(task)
            await session.flush()
            reminder = Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='due_soon', fire_at=now, status='sent')
            session.add(reminder)
            await session.commit()
            offer = await reminder_action(reminder.id, ReminderActionRequest(action='reschedule'), session, OWNER)
            assert len(offer['slots']) == 3
            chosen = offer['slots'][1]['start_at']
            moved = await reschedule(reminder.id, RescheduleRequest(start_at=chosen), session, OWNER)
            assert moved['status'] == 'pending' and moved['plan_block']['start_at'] == chosen
    with_factory(body)


def test_snooze_is_logged_for_analytics():
    async def body(factory):
        from app.services.reminder_worker import apply_reminder_action
        now = datetime.now(timezone.utc)
        async with factory() as session:
            task = Task(user_id=OWNER, title='Rent', category='finance', created_at=now)
            session.add(task)
            await session.flush()
            reminder = Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='due_soon', fire_at=now, status='sent')
            session.add(reminder)
            await session.flush()
            await apply_reminder_action(session, user_id=OWNER, reminder_id=reminder.id, action='snooze_15')
            event = (await session.execute(select(ActivityEvent).where(ActivityEvent.type == 'reminder_snoozed'))).scalar_one()
            assert event.payload['category'] == 'finance' and reminder.status == 'pending'
    with_factory(body)


def _push_settings():
    return SimpleNamespace(vapid_private_key='k', vapid_subject='mailto:x@example.com',
                           push_allowed_host_list=['fcm.googleapis.com'])


def test_worker_delivers_once_merges_within_ten_minutes_and_marks_missed(monkeypatch):
    async def body(factory):
        from app import worker
        from app.services.push_service import PushResult
        sent_payloads = []

        async def fake_send(subscriptions, payload, settings):
            sent_payloads.append(payload)
            return PushResult(len(subscriptions), ['https://fcm.googleapis.com/gone'])
        monkeypatch.setattr(worker, 'send_to_subscriptions', fake_send)
        now = datetime.now(timezone.utc)
        async with factory() as session:
            task = Task(user_id=OWNER, title='Report', created_at=now)
            session.add(task)
            await session.flush()
            session.add_all([
                PushSubscription(user_id=OWNER, endpoint='https://fcm.googleapis.com/gone', p256dh='a', auth='b'),
                Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='custom', fire_at=now - timedelta(seconds=5), message='one'),
                Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='due_soon', fire_at=now - timedelta(seconds=1), message='two'),
                Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='overdue', fire_at=now - timedelta(hours=3), message='old'),
            ])
            await session.commit()
        report = await worker.deliver_due(factory, _push_settings(), now=now)
        assert (report['sent'], report['deferred'], report['missed'], report['retry']) == (2, 0, 1, 0)
        assert len(sent_payloads) == 1 and sent_payloads[0]['body'].startswith('2 reminders')
        async with factory() as session:
            assert not (await session.execute(select(PushSubscription))).scalars().all()  # 410 Gone removed
            statuses = sorted(r.status for r in (await session.execute(select(Reminder))).scalars())
            assert statuses == ['missed', 'sent', 'sent']
            session.add(Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='custom',
                                 fire_at=now + timedelta(minutes=1), message='three'))
            await session.commit()
        later = await worker.deliver_due(factory, _push_settings(), now=now + timedelta(minutes=2))
        assert later['deferred'] == 1 and len(sent_payloads) == 1  # rate limit: wait, then summarize
        async with factory() as session, session.begin():
            await worker.heartbeat(session, 'w1', now=now, jobs={})
        async with factory() as session:
            assert (await session.get(WorkerStatus, 'w1')) is not None
    with_factory(body)


def test_transient_push_failure_stays_retryable(monkeypatch):
    async def body(factory):
        from app import worker
        from app.services.push_service import PushResult

        async def failing(subscriptions, payload, settings):
            return PushResult(0, [], failed=len(subscriptions), statuses=[503])
        monkeypatch.setattr(worker, 'send_to_subscriptions', failing)
        now = datetime.now(timezone.utc)
        async with factory() as session:
            task = Task(user_id=OWNER, title='Report', created_at=now)
            session.add(task)
            await session.flush()
            session.add_all([PushSubscription(user_id=OWNER, endpoint='https://fcm.googleapis.com/a', p256dh='a', auth='b'),
                             Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='custom', fire_at=now, message='x')])
            await session.commit()
        report = await worker.deliver_due(factory, _push_settings(), now=now)
        assert report['retry'] == 1 and report['sent'] == 0
        async with factory() as session:
            reminder = (await session.execute(select(Reminder))).scalar_one()
            assert reminder.status == 'pending' and reminder.sent_at is None
    with_factory(body)


def test_one_failing_job_does_not_stop_the_others(monkeypatch):
    async def body(factory):
        from app import worker
        calls = []

        async def broken(factory, *, now):
            raise RuntimeError('boom')

        async def fine(factory, *, now):
            calls.append('retention')
            return {}
        monkeypatch.setitem(worker.JOBS, 'rescore', (timedelta(hours=1), broken))
        monkeypatch.setitem(worker.JOBS, 'retention', (timedelta(hours=24), fine))
        report = await worker.run_cycle(factory, _push_settings(), name='w', now=datetime.now(timezone.utc))
        assert report['rescore'] == 'failed' and calls == ['retention']
        async with factory() as session:
            assert (await session.get(WorkerStatus, 'w')) is not None  # heartbeat still written
    with_factory(body)


def test_daily_plan_is_attempted_once_per_day():
    async def body(factory):
        from app import worker
        now = datetime.now(timezone.utc).replace(hour=12)
        async with factory() as session:
            session.add(Task(user_id=OWNER, title='Someday', created_at=now))
            await session.commit()
        first = await worker.daily_plans(factory, now=now)
        second = await worker.daily_plans(factory, now=now + timedelta(minutes=15))
        async with factory() as session:
            markers = (await session.execute(select(ActivityEvent).where(ActivityEvent.type == 'daily_plan_built'))).scalars().all()
        assert first['failed'] == second['failed'] == 0 and len(markers) == 1
    with_factory(body)


def test_push_endpoints_are_limited_to_push_services():
    from app.services.push_service import allowed_endpoint
    hosts = ['fcm.googleapis.com', 'push.apple.com']
    assert allowed_endpoint('https://fcm.googleapis.com/fcm/send/abc', hosts)
    assert allowed_endpoint('https://web.push.apple.com/xyz', hosts)
    assert not allowed_endpoint('https://169.254.169.254/latest/meta-data', hosts)
    assert not allowed_endpoint('https://fcm.googleapis.com.evil.example/x', hosts)
    assert not allowed_endpoint('http://fcm.googleapis.com/x', hosts)
    assert not allowed_endpoint('https://fcm.googleapis.com:8443/x', hosts)


def test_subscribe_upserts_and_moves_endpoint_to_current_user():
    async def body(factory):
        from app.api.push import SubscriptionIn, subscribe
        endpoint = 'https://fcm.googleapis.com/fcm/send/device1'
        async with factory() as session:
            await subscribe(SubscriptionIn(endpoint=endpoint, keys={'p256dh': 'a', 'auth': 'b'}), session, 'user_first')
            await subscribe(SubscriptionIn(endpoint=endpoint, keys={'p256dh': 'c', 'auth': 'd'}), session, 'user_second')
            await subscribe(SubscriptionIn(endpoint=endpoint, keys={'p256dh': 'e', 'auth': 'f'}), session, 'user_second')
            rows = (await session.execute(select(PushSubscription))).scalars().all()
            assert [(r.user_id, r.p256dh) for r in rows] == [('user_second', 'e')]
        with pytest.raises(Exception):
            SubscriptionIn(endpoint='https://internal.example/hook', keys={'p256dh': 'a', 'auth': 'b'})
    with_factory(body)


def test_actual_effort_endpoint():
    async def body(factory):
        from fastapi import HTTPException
        from app.api.tasks import ActualEffort, record_actual_effort
        now = datetime.now(timezone.utc)
        async with factory() as session:
            open_task = Task(user_id=OWNER, title='Open', effort_est_min=60, created_at=now)
            done_task = Task(user_id=OWNER, title='Done', effort_est_min=60, status='done', completed_at=now, created_at=now)
            session.add_all([open_task, done_task])
            await session.commit()
            with pytest.raises(HTTPException) as error:
                await record_actual_effort(open_task.id, ActualEffort(answer='more'), session, OWNER)
            assert error.value.status_code == 409
            with pytest.raises(HTTPException) as error:
                await record_actual_effort(done_task.id, ActualEffort(answer='custom'), session, OWNER)
            assert error.value.status_code == 422
            for answer, expected in (('less', 45), ('about_right', 60), ('more', 90)):
                result = await record_actual_effort(done_task.id, ActualEffort(answer=answer), session, OWNER)
                assert result.effort_actual_min == expected
            result = await record_actual_effort(done_task.id, ActualEffort(answer='custom', minutes=73), session, OWNER)
            assert result.effort_actual_min == 73
    with_factory(body)


def test_extension_limit_respects_quiet_hours_and_routine_moves_avoid_bookings():
    from datetime import time
    from app.services.conflict_service import extension_limit, free_destination
    from app.services.scheduler import BusyBlock
    assert extension_limit(time(18), time(22, 30), time(7, 30)) == time(21)
    assert extension_limit(time(18), time(19), time(23)) == time(19)
    assert extension_limit(time(18), time(8), time(20)) == time(18)  # daytime quiet hours: no extension
    deadline = datetime(2026, 11, 18, 9, tzinfo=timezone.utc)
    gym = BusyBlock(datetime(2026, 11, 17, 7, tzinfo=timezone.utc), datetime(2026, 11, 17, 8, tzinfo=timezone.utc))
    next_gym = BusyBlock(datetime(2026, 11, 18, 7, tzinfo=timezone.utc) + timedelta(days=1),
                         datetime(2026, 11, 18, 8, tzinfo=timezone.utc) + timedelta(days=1))
    moved = free_destination(gym, deadline, [next_gym])
    assert moved is not None and moved > deadline and not (next_gym.start < moved + timedelta(hours=1) and moved < next_gym.end)


def test_export_and_delete_account_remove_every_row():
    async def body(factory):
        from app.api.account import delete_account, export_data
        now = datetime.now(timezone.utc)
        async with factory() as session:
            session.add(User(id=OWNER))
            session.add(Task(user_id=OWNER, title='Mine', created_at=now))
            session.add(Task(user_id='user_other', title='Theirs', created_at=now))
            session.add(PushSubscription(user_id=OWNER, endpoint='https://fcm.googleapis.com/1', p256dh='secret', auth='secret'))
            session.add(Message(user_id=OWNER, role='user', text='hello'))
            await session.commit()
            data = await export_data(session, OWNER)
            assert [t['title'] for t in data['tasks']] == ['Mine']
            assert 'p256dh' not in data['push_subscriptions'][0]
            assert 'auth' not in data['push_subscriptions'][0]
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as error:
                await delete_account(False, session, OWNER)
            assert error.value.status_code == 409
            await delete_account(True, session, OWNER)
            assert [t.title for t in (await session.execute(select(Task))).scalars()] == ['Theirs']
            assert not (await session.execute(select(PushSubscription))).scalars().all()
    with_factory(body)


def test_cors_preflight_is_answered_before_auth():
    from app.main import app
    with TestClient(app) as client:
        response = client.options('/api/tasks', headers={'Origin': 'http://localhost:3000',
                                                         'Access-Control-Request-Method': 'GET',
                                                         'Access-Control-Request-Headers': 'authorization'})
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
        denied = client.options('/api/tasks', headers={'Origin': 'https://evil.example',
                                                       'Access-Control-Request-Method': 'GET'})
        assert 'access-control-allow-origin' not in denied.headers


def test_calibrated_effort_feeds_priority_why():
    async def body(factory):
        from app.services.planning_service import recalculate_priorities
        now = datetime.now(timezone.utc)
        await seed_priya(factory, now.date())
        async with factory() as session:
            await recalculate_priorities(session, OWNER, now)
            report = (await session.execute(select(Task).where(Task.title == '[Demo] Finish DBMS report'))).scalar_one()
            assert report.priority_breakdown['effort_min'] == 288  # 180 min x 1.6 study factor
            assert '1.6' in report.priority_why
    with_factory(body)
