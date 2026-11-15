"""PRD items finished late: inferred preferences (F6), nightly/Sunday worker jobs, end-of-day
check-in (5.6), dependency listing (F2.5) and the per-day adherence series for Insights sparklines."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import (ActivityEvent, Base, PlanBlock, Preference, Reminder, Suggestion, Task, TaskDependency,
                        WorkerStatus)

OWNER = 'user_prd_remaining'
SUNDAY = date(2026, 11, 15)  # a Sunday


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


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


async def add_sent_reminders(session, *, snoozed: int, total: int = 5, now: datetime):
    """`total` sent 'start now' reminders, the newest `snoozed` of them snoozed."""
    task = Task(user_id=OWNER, title='Report', created_at=now - timedelta(days=3))
    session.add(task)
    await session.flush()
    ids = []
    for index in range(total):
        reminder = Reminder(user_id=OWNER, item_type='task', item_id=task.id, kind='start_now',
                            fire_at=now - timedelta(hours=index + 1), status='sent',
                            sent_at=now - timedelta(hours=index + 1))
        session.add(reminder)
        await session.flush()
        ids.append(reminder.id)
        if index < snoozed:
            session.add(ActivityEvent(user_id=OWNER, type='reminder_snoozed', entity_id=reminder.id,
                                      occurred_at=now - timedelta(hours=index + 1),
                                      payload={'kind': 'start_now', 'category': 'other', 'action': 'snooze_15'}))
    await session.flush()
    return task, ids


def add_moves(session, hours: list[int], *, now: datetime):
    for offset, hour in enumerate(hours):
        session.add(ActivityEvent(user_id=OWNER, type='block_moved', entity_id=uuid4(),
                                  occurred_at=now - timedelta(days=offset), payload={'hour': hour}))


async def proposals(session) -> dict:
    rows = (await session.execute(select(Preference).where(Preference.user_id == OWNER,
        Preference.key.like('inferred.%')))).scalars().all()
    return {row.key: row for row in rows}


# ---------- F6 inference rules ----------

def test_four_of_last_five_snoozes_propose_a_later_reminder():
    async def body(factory):
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            await add_sent_reminders(session, snoozed=4, now=now)
            written = await run_inference(session, OWNER, now=now)
            assert [row.key for row in written] == ['inferred.reminder_lead']
            row = (await proposals(session))['inferred.reminder_lead']
            # Default lead is 60 min; a smaller buffer fires the reminder 15 min later.
            assert row.value == {'minutes': 45}
            assert (row.source, row.status) == ('inferred', 'suggested')
            assert row.confidence == pytest.approx(0.8) and row.confidence < 1
            # Running the rules again writes nothing new.
            assert await run_inference(session, OWNER, now=now) == []
            assert len(await proposals(session)) == 1
    with_factory(body)


@pytest.mark.parametrize('snoozed,total', [(3, 5), (4, 4)])
def test_snooze_rule_needs_four_of_five_sends(snoozed, total):
    async def body(factory):
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            await add_sent_reminders(session, snoozed=snoozed, total=total, now=now)
            assert await run_inference(session, OWNER, now=now) == []
    with_factory(body)


def test_snooze_rule_steps_down_from_the_current_lead_and_stops_at_zero():
    async def body(factory):
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            session.add(Preference(user_id=OWNER, key='reminder_lead', value={'minutes': 10}))
            await add_sent_reminders(session, snoozed=5, now=now)
            await run_inference(session, OWNER, now=now)
            row = (await proposals(session))['inferred.reminder_lead']
            assert row.value == {'minutes': 0} and row.confidence == pytest.approx(0.9)
            await session.commit()
        async with factory() as session:
            lead = (await session.execute(select(Preference).where(Preference.key == 'reminder_lead'))).scalar_one()
            lead.value = {'minutes': 0}
            await session.delete((await proposals(session))['inferred.reminder_lead'])
            await session.flush()
            assert await run_inference(session, OWNER, now=now) == []  # nothing later to offer
    with_factory(body)


def test_three_moves_to_the_same_hour_propose_a_focus_window():
    async def body(factory):
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            add_moves(session, [15, 15, 9, 15], now=now)
            await session.flush()
            await run_inference(session, OWNER, now=now)
            row = (await proposals(session))['inferred.focus_windows']
            assert row.value == {'windows': [['15:00', '17:00']]}
            assert row.status == 'suggested' and row.confidence == pytest.approx(0.6)
    with_factory(body)


def test_move_rule_ignores_two_moves_old_moves_and_matching_windows():
    async def body(factory):
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            add_moves(session, [15, 15], now=now)
            # A third move, but outside the 14-day window.
            session.add(ActivityEvent(user_id=OWNER, type='block_moved', occurred_at=now - timedelta(days=20),
                                      payload={'hour': 15}))
            await session.flush()
            assert await run_inference(session, OWNER, now=now) == []
            add_moves(session, [10, 10, 10], now=now)
            session.add(Preference(user_id=OWNER, key='focus_windows', value={'windows': [['10:00', '12:00']]}))
            await session.flush()
            assert await run_inference(session, OWNER, now=now) == []  # already the focus window
    with_factory(body)


def test_late_evening_window_ends_before_midnight_and_validates():
    async def body(factory):
        from app.services.preference_inference import run_inference
        from app.services.preference_values import validate_preference
        now = at(SUNDAY, 12)
        async with factory() as session:
            add_moves(session, [23, 23, 23], now=now)
            await session.flush()
            await run_inference(session, OWNER, now=now)
            row = (await proposals(session))['inferred.focus_windows']
            assert row.value == {'windows': [['23:00', '23:59']]}
            validate_preference('focus_windows', row.value)
    with_factory(body)


def test_planner_ignores_a_proposal_until_it_is_accepted():
    async def body(factory):
        from app.api.preferences import accept_preference
        from app.services.planning_service import active_preferences
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            session.add(Preference(user_id=OWNER, key='reminder_lead', value={'minutes': 60}))
            await add_sent_reminders(session, snoozed=4, now=now)
            await run_inference(session, OWNER, now=now)
            await session.commit()
            assert (await active_preferences(session, OWNER))['reminder_lead'] == {'minutes': 60}
            row = (await proposals(session))['inferred.reminder_lead']
            result = await accept_preference(row.id, session, OWNER)
            assert result['preference']['key'] == 'reminder_lead'
            assert result['preference']['value'] == {'minutes': 45}
            assert result['preference']['source'] == 'inferred' and result['preference']['status'] == 'active'
            assert result['action_id']
            assert await proposals(session) == {}
            assert (await active_preferences(session, OWNER))['reminder_lead'] == {'minutes': 45}
    with_factory(body)


def test_accepting_creates_the_target_preference_when_none_exists():
    async def body(factory):
        from app.api.preferences import accept_preference
        from app.services.planning_service import active_preferences
        from app.services.preference_inference import run_inference
        now = at(SUNDAY, 12)
        async with factory() as session:
            add_moves(session, [8, 8, 8], now=now)
            await session.flush()
            await run_inference(session, OWNER, now=now)
            await session.commit()
            row = (await proposals(session))['inferred.focus_windows']
            await accept_preference(row.id, session, OWNER)
            assert (await active_preferences(session, OWNER))['focus_windows'] == {'windows': [['08:00', '10:00']]}
    with_factory(body)


def test_deleting_a_proposal_stops_it_coming_back():
    async def body(factory):
        from app.api.preferences import delete_preference
        from app.services.preference_inference import run_inference
        now = datetime.now(timezone.utc)  # the dismissal is stamped with the real clock
        async with factory() as session:
            await add_sent_reminders(session, snoozed=4, now=now)
            await run_inference(session, OWNER, now=now)
            await session.commit()
            row = (await proposals(session))['inferred.reminder_lead']
            await delete_preference(row.id, True, session, OWNER)
            dismissed = (await session.execute(select(ActivityEvent).where(
                ActivityEvent.type == 'preference_dismissed'))).scalar_one()
            assert dismissed.payload == {'key': 'reminder_lead', 'value': {'minutes': 45}}
            assert await run_inference(session, OWNER, now=now) == []
            assert await proposals(session) == {}
            # After the 30-day cool-down the same pattern may be offered again.
            assert len(await run_inference(session, OWNER, now=now + timedelta(days=31))) == 1
    with_factory(body)


def test_user_cannot_post_an_inferred_key_directly():
    from pydantic import ValidationError
    from app.schemas_preferences import PreferenceUpdate
    with pytest.raises(ValidationError):
        PreferenceUpdate(key='inferred.reminder_lead', value={'minutes': 5})


def test_snooze_from_the_app_runs_the_rules():
    async def body(factory):
        from app.api.reminder_actions import reminder_action
        from app.schemas_reminders import ReminderActionRequest
        now = datetime.now(timezone.utc)
        async with factory() as session:
            # 3 of the last 5 already snoozed; the newest one is still unanswered.
            task, ids = await add_sent_reminders(session, snoozed=0, now=now)
            for reminder_id in ids[1:4]:
                session.add(ActivityEvent(user_id=OWNER, type='reminder_snoozed', entity_id=reminder_id,
                                          occurred_at=now, payload={'kind': 'start_now', 'category': 'other'}))
            await session.commit()
            await reminder_action(ids[0], ReminderActionRequest(action='snooze_15'), session, OWNER)
            assert (await proposals(session))['inferred.reminder_lead'].value == {'minutes': 45}
    with_factory(body)


def test_moving_a_block_logs_the_local_hour_and_three_moves_propose_it():
    async def body(factory):
        from app.api.plan_blocks import patch_block
        from app.schemas_plan_blocks import PlanBlockPatch
        async with factory() as session:
            session.add(Preference(user_id=OWNER, key='timezone', value={'name': 'Asia/Kolkata'}))
            task = Task(user_id=OWNER, title='Essay', effort_est_min=60, created_at=datetime.now(timezone.utc))
            session.add(task)
            await session.flush()
            block = PlanBlock(user_id=OWNER, task_id=task.id, start_at=at(SUNDAY + timedelta(days=30), 4),
                              end_at=at(SUNDAY + timedelta(days=30), 5), plan_date=at(SUNDAY + timedelta(days=30), 0))
            session.add(block)
            await session.commit()
            for day in range(31, 34):
                # 09:30 UTC is 15:00 in Kolkata.
                start = at(SUNDAY + timedelta(days=day), 9, 30)
                await patch_block(block.id, PlanBlockPatch(start_at=start, end_at=start + timedelta(hours=1)),
                                  session, OWNER)
            moves = (await session.execute(select(ActivityEvent).where(ActivityEvent.type == 'block_moved'))).scalars().all()
            assert [move.payload['hour'] for move in moves] == [15, 15, 15]
            assert (await proposals(session))['inferred.focus_windows'].value == {'windows': [['15:00', '17:00']]}
            # A status-only change is not a move.
            await patch_block(block.id, PlanBlockPatch(status='done'), session, OWNER)
            assert len((await session.execute(select(ActivityEvent).where(
                ActivityEvent.type == 'block_moved'))).scalars().all()) == 3
    with_factory(body)


# ---------- worker jobs ----------

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


def test_weekly_insights_run_once_on_sunday_evening():
    async def body(factory):
        from app import worker
        sunday_evening = at(SUNDAY, 19)
        await seed_priya(factory, SUNDAY)
        async with factory() as session:
            old = Suggestion(user_id=OWNER, type='protect_routine', text='Old idea', payload={}, status='active',
                             created_at=sunday_evening - timedelta(days=7))
            session.add(old)
            await session.commit()
        async with factory() as session, session.begin():
            assert await worker.weekly_insight(session, OWNER, now=at(SUNDAY - timedelta(days=1), 19)) is False  # Saturday
            assert await worker.weekly_insight(session, OWNER, now=at(SUNDAY, 17)) is False  # too early
        report = await worker.weekly_insights(factory, now=sunday_evening)
        assert report['failed'] == 0 and report['done'] == 1
        again = await worker.weekly_insights(factory, now=sunday_evening + timedelta(hours=1))
        assert again['done'] == 0
        async with factory() as session:
            rows = (await session.execute(select(Suggestion).order_by(Suggestion.created_at))).scalars().all()
            assert rows[0].text == 'Old idea' and rows[0].status == 'expired'
            fresh = [row for row in rows[1:] if row.status == 'active']
            assert fresh and fresh[0].type == 'pad_estimates' and '1.6' in fresh[0].text
            markers = (await session.execute(select(ActivityEvent).where(
                ActivityEvent.type == 'weekly_insights_built'))).scalars().all()
            assert len(markers) == 1
    with_factory(body)


def test_weekly_insights_use_the_users_local_sunday():
    async def body(factory):
        from app import worker
        async with factory() as session:
            session.add(Preference(user_id=OWNER, key='timezone', value={'name': 'Asia/Kolkata'}))
            session.add(Task(user_id=OWNER, title='Open', created_at=at(SUNDAY, 0)))
            await session.commit()
        async with factory() as session, session.begin():
            # 13:00 UTC Sunday is 18:30 Sunday in Kolkata: due.
            assert await worker.weekly_insight(session, OWNER, now=at(SUNDAY, 13)) is False  # nothing to suggest yet
            built = (await session.execute(select(ActivityEvent).where(
                ActivityEvent.type == 'weekly_insights_built'))).scalars().all()
            assert len(built) == 1
        async with factory() as session, session.begin():
            # 19:00 UTC Sunday is already Monday in Kolkata: not due.
            await session.execute(ActivityEvent.__table__.delete())
            assert await worker.weekly_insight(session, OWNER, now=at(SUNDAY, 19)) is False
            assert not (await session.execute(select(ActivityEvent))).scalars().all()
    with_factory(body)


def test_nightly_analytics_runs_inference_for_active_users():
    async def body(factory):
        from app import worker
        now = at(SUNDAY, 2)
        async with factory() as session:
            await add_sent_reminders(session, snoozed=4, now=now)
            await session.commit()
        report = await worker.analytics_all(factory, now=now)
        assert report == {'users': 1, 'done': 1, 'failed': 0}
        async with factory() as session:
            assert 'inferred.reminder_lead' in await proposals(session)
        assert (await worker.analytics_all(factory, now=now))['done'] == 0  # nothing new
    with_factory(body)


def test_new_jobs_are_scheduled_and_safe_on_an_empty_database():
    async def body(factory):
        from app import worker
        from app.config import get_settings
        assert {'analytics', 'weekly_insights'} <= set(worker.JOBS)
        assert worker.JOBS['analytics'][0] == timedelta(hours=24)
        report = await worker.run_cycle(factory, get_settings(), name='w', now=at(SUNDAY, 19))
        assert report['analytics'] == {'users': 0, 'done': 0, 'failed': 0}
        assert report['weekly_insights'] == {'users': 0, 'done': 0, 'failed': 0}
        async with factory() as session:
            status = await session.get(WorkerStatus, 'w')
            assert {'analytics', 'weekly_insights'} <= set(status.last_jobs)
    with_factory(body)


# ---------- end-of-day check-in ----------

async def checkin_day(session):
    """Today (Sunday, UTC): a missed morning block, a done block and a block later tonight."""
    late, done, missed_task = (Task(user_id=OWNER, title=title, effort_est_min=60, created_at=at(SUNDAY, 0))
                               for title in ('Night reading', 'Groceries', 'DBMS report'))
    session.add_all([late, done, missed_task])
    await session.flush()
    missed = PlanBlock(user_id=OWNER, task_id=missed_task.id, start_at=at(SUNDAY, 9), end_at=at(SUNDAY, 10),
                       plan_date=at(SUNDAY, 0))
    finished = PlanBlock(user_id=OWNER, task_id=done.id, start_at=at(SUNDAY, 11), end_at=at(SUNDAY, 12),
                         status='done', plan_date=at(SUNDAY, 0))
    tonight = PlanBlock(user_id=OWNER, task_id=late.id, start_at=at(SUNDAY, 22), end_at=at(SUNDAY, 23),
                        plan_date=at(SUNDAY, 0))
    yesterday = PlanBlock(user_id=OWNER, task_id=missed_task.id, start_at=at(SUNDAY - timedelta(days=1), 9),
                          end_at=at(SUNDAY - timedelta(days=1), 10), plan_date=at(SUNDAY - timedelta(days=1), 0))
    session.add_all([missed, finished, tonight, yesterday])
    await session.commit()
    return missed_task, missed


def test_checkin_lists_unfinished_blocks_and_is_due_at_nine_pm():
    async def body(factory):
        from app.api.today import checkin_state
        async with factory() as session:
            _, missed = await checkin_day(session)
            state = await checkin_state(session, OWNER, now=at(SUNDAY, 21, 30))
            assert state['due'] is True and state['checkin_time'] == '21:00'
            assert [(b['id'], b['title']) for b in state['blocks']] == [(str(missed.id), 'DBMS report')]
            early = await checkin_state(session, OWNER, now=at(SUNDAY, 20))
            assert early['due'] is False and len(early['blocks']) == 1
    with_factory(body)


def test_checkin_is_not_due_when_everything_was_done():
    async def body(factory):
        from app.api.today import checkin_state
        async with factory() as session:
            _, missed = await checkin_day(session)
            missed.status = 'done'
            await session.commit()
            state = await checkin_state(session, OWNER, now=at(SUNDAY, 21, 30))
            assert state == {**state, 'due': False, 'blocks': []}
    with_factory(body)


def test_move_to_tomorrow_replans_the_work_on_the_next_day():
    async def body(factory):
        from app.api.today import CheckinAction, apply_checkin_action
        async with factory() as session:
            task, missed = await checkin_day(session)
            result = await apply_checkin_action(session, OWNER, CheckinAction(action='move_to_tomorrow',
                                                block_ids=[missed.id]), now=at(SUNDAY, 21, 30))
            assert result['action'] == 'move_to_tomorrow' and result['moved'] == 1
            assert result['placed'] and result['unplaced_task_ids'] == []
            tomorrow = SUNDAY + timedelta(days=1)
            for block in result['placed']:
                assert block['task_id'] == str(task.id)
                start = block['start_at'].replace(tzinfo=timezone.utc) if block['start_at'].tzinfo is None else block['start_at']
                assert start >= at(tomorrow, 0)
            await session.refresh(missed)
            assert missed.status == 'moved'
            event = (await session.execute(select(ActivityEvent).where(
                ActivityEvent.type == 'checkin_move_to_tomorrow'))).scalar_one()
            assert event.payload == {'blocks': 1}
    with_factory(body)


def test_drop_gives_up_the_task_and_can_be_undone_as_a_batch():
    async def body(factory):
        from app.api.today import CheckinAction, apply_checkin_action
        async with factory() as session:
            task, missed = await checkin_day(session)
            result = await apply_checkin_action(session, OWNER, CheckinAction(action='drop', block_ids=[missed.id]),
                                                now=at(SUNDAY, 21, 30))
            assert result['dropped_tasks'] == 1 and len(result['batch_ids']) == 1
            await session.refresh(task)
            await session.refresh(missed)
            assert task.status == 'dropped' and missed.status == 'missed'
    with_factory(body)


def test_checkin_rejects_blocks_that_are_not_unfinished_today():
    async def body(factory):
        from app.api.today import CheckinAction, apply_checkin_action
        async with factory() as session:
            await checkin_day(session)
            tonight = (await session.execute(select(PlanBlock).where(PlanBlock.start_at == at(SUNDAY, 22)))).scalar_one()
            for block_id in (tonight.id, uuid4()):
                with pytest.raises(HTTPException) as error:
                    await apply_checkin_action(session, OWNER, CheckinAction(action='drop', block_ids=[block_id]),
                                               now=at(SUNDAY, 21, 30))
                assert error.value.status_code == 409
    with_factory(body)


def test_checkin_payload_is_validated():
    from pydantic import ValidationError
    from app.api.today import CheckinAction
    for bad in ({'action': 'snooze', 'block_ids': [str(uuid4())]}, {'action': 'drop', 'block_ids': []},
                {'action': 'drop', 'block_ids': [str(uuid4())], 'user_id': 'someone'}):
        with pytest.raises(ValidationError):
            CheckinAction(**bad)


def test_checkin_only_sees_the_callers_blocks():
    async def body(factory):
        from app.api.today import checkin_state
        async with factory() as session:
            await checkin_day(session)
            assert (await checkin_state(session, 'user_someone_else', now=at(SUNDAY, 21, 30)))['blocks'] == []
    with_factory(body)


# ---------- dependencies and insight series ----------

def test_dependency_links_are_listed_for_the_owner_only():
    async def body(factory):
        from app.api.tasks import list_dependencies
        async with factory() as session:
            first, second = Task(user_id=OWNER, title='Outline'), Task(user_id=OWNER, title='Draft')
            session.add_all([first, second])
            await session.flush()
            session.add(TaskDependency(user_id=OWNER, task_id=second.id, depends_on_task_id=first.id))
            session.add(TaskDependency(user_id='user_other', task_id=uuid4(), depends_on_task_id=uuid4()))
            await session.commit()
            assert await list_dependencies(session, OWNER) == [
                {'task_id': str(second.id), 'depends_on_task_id': str(first.id)}]
    with_factory(body)


def test_new_routes_are_registered():
    from app.api.tasks import router as tasks
    from app.api.today import router as today
    paths = [(route.path, sorted(route.methods)) for router in (tasks, today) for route in router.routes]
    assert ('/api/tasks/dependencies', ['GET']) in paths
    # No GET /api/tasks/{task_id} exists to swallow "dependencies" as an id.
    assert not any(path == '/api/tasks/{task_id}' and 'GET' in methods for path, methods in paths)
    assert ('/api/today/checkin', ['GET']) in paths and ('/api/today/checkin', ['POST']) in paths


def test_adherence_series_matches_planned_and_done_blocks():
    async def body(factory):
        from app.services.insight_service import compute_user_insights
        now = at(SUNDAY, 20)
        await seed_priya(factory, SUNDAY)
        async with factory() as session:
            data = await compute_user_insights(session, OWNER, now=now)
            series = data['adherence_chart']
            assert len(series) == 14 and series[-1]['date'] == SUNDAY.isoformat()
            assert sum(day['planned'] for day in series) == data['planned_blocks_14d']
            for day in series:
                assert day['rate'] is None if not day['planned'] else day['rate'] == round(day['done'] / day['planned'], 2)
    with_factory(body)
