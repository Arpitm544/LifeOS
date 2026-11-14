"""Workflow regressions use SQLite; PostgreSQL concurrency is covered separately."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base, Task, Routine, Preference, Reminder, Event, PlanBlock, ActionLog
from app.schemas import TaskCreate, TaskPatch
from app.schemas_plan_blocks import PlanBlockCreate, PlanBlockPatch
from app.schemas_preferences import RoutineCreate
from app.api.tasks import edit_task, delete_task, set_dependencies, DependenciesUpdate
from app.api.task_batches import edit_batch, BatchEdit
from app.api.actions import undo_batch
from app.api.plan_blocks import create_block, patch_block
from app.api.preferences import create_routine, move_instance, RoutineInstanceEdit
from app.services.task_service import create_task
from app.services.domain_service import undo_logged_action, sync_reminders
from app.services.reminder_worker import apply_reminder_action
from app.services.planning_service import busy_for_window


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


def test_task_mutations_priorities_reminder_completion_and_delete_undo():
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        owner = 'user_workflow'
        now = datetime.now(timezone.utc)
        async with factory() as session:
            # Zero work time forces calendar urgency; the old fixed 40h gives P3.
            session.add(Preference(user_id=owner, key='focus_windows', value={'windows': [['00:00', '00:00']]}))
            task = await create_task(session, owner, TaskCreate(title='Report', deadline_at=now+timedelta(days=3)))
            assert task.priority_score >= 60
            other = await create_task(session, owner, TaskCreate(title='Review', depends_on=[task.id]))
            assert other.status == 'blocked'
            assert task.priority_score >= 65  # Includes the dependent count.
            await session.commit()
            initial = task.priority_score
            await edit_task(task.id, TaskPatch(importance=5), session, owner)
            assert task.priority_score > initial
            response = await edit_batch(BatchEdit(task_ids=[task.id], changes=TaskPatch(importance=1)), session, owner)
            batch_log = await session.get(ActionLog, UUID(response['action_ids'][0]))
            assert batch_log.after['priority_score'] == task.priority_score < initial
            assert other.importance == 3
            # Completion from a reminder unblocks dependents and leaves an undo action.
            reminder = Reminder(user_id=owner, item_type='task', item_id=task.id, kind='due_soon', fire_at=now, status='sent')
            session.add(reminder)
            await session.flush()
            await apply_reminder_action(session, user_id=owner, reminder_id=reminder.id, action='done')
            await session.commit()
            assert task.status == 'done' and other.status == 'open'
            log = (await session.execute(select(ActionLog).where(ActionLog.entity_id == task.id,
                ActionLog.action_type == 'complete'))).scalar_one()
            await undo_logged_action(session, owner, log.id)
            await session.commit()
            assert task.status == 'open' and other.status == 'blocked'
            # Deletion removes future planned work and restores both in one Undo.
            block = PlanBlock(user_id=owner, task_id=task.id, start_at=now+timedelta(hours=1),
                end_at=now+timedelta(hours=2), plan_date=now)
            session.add(block)
            await session.commit()
            block_id = block.id
            await delete_task(task.id, True, session, owner)
            assert await session.get(PlanBlock, block_id) is None
            log = (await session.execute(select(ActionLog).where(ActionLog.entity_id == task.id,
                ActionLog.action_type == 'delete'))).scalar_one()
            await undo_batch(log.batch_id, session, owner)
            assert task.status == 'open' and await session.get(PlanBlock, block_id) is not None
            from unittest.mock import AsyncMock
            import httpx
            from app.services.chat_orchestrator import handle_chat
            provider = AsyncMock()
            provider.parse.side_effect = httpx.ReadTimeout('outage')
            fallback = await handle_chat(session, user_id=owner, text='Buy milk', client_tz='UTC', llm=provider)
            assert fallback['fallback'] and len(fallback['actions']) == 1
            saved = await session.get(Task, UUID(fallback['actions'][0]['task_id']))
            assert saved.title == 'Buy milk'
            # Quiet-hours collisions produce one notification per timestamp.
            task.deadline_at = now.replace(hour=3, minute=0, second=0, microsecond=0)+timedelta(days=2)
            await sync_reminders(session, owner, task)
            await session.flush()
            pending = (await session.execute(select(Reminder).where(Reminder.item_id == task.id,
                Reminder.status == 'pending'))).scalars().all()
            assert len(pending) == len({row.fire_at for row in pending}) == 1
        await engine.dispose()
    asyncio.run(run())


def test_routine_creation_calendar_fail_closed_and_block_dates():
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        owner = 'user_calendar'
        async with factory() as session:
            session.add(Preference(user_id=owner, key='timezone', value={'name': 'Asia/Kolkata'}))
            await session.commit()
            result = await create_routine(RoutineCreate(title='Gym', rrule='FREQ=DAILY;COUNT=3',
                start_time='07:00', duration_min=30, movable=False), session, owner)
            assert result['anchor_date'] == datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
            routine = await session.get(Routine, UUID(result['id']))
            with pytest.raises(HTTPException) as exc:
                await move_instance(routine.id, RoutineInstanceEdit(original_start=datetime.now(timezone.utc),
                    start_at=datetime.now(timezone.utc), duration_min=30), session=session, user_id=owner)
            assert exc.value.status_code == 409 and routine.overrides == {}
            # A recurring event whose base interval is outside the window is still busy.
            start = datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
            session.add(Event(user_id=owner, title='Daily', start_at=start-timedelta(days=1),
                end_at=start-timedelta(days=1)+timedelta(hours=1), rrule='FREQ=DAILY;COUNT=3'))
            await session.flush()
            busy = await busy_for_window(session, owner, start, start+timedelta(days=1), ZoneInfo('UTC'))
            assert any(slot.start == start and slot.end == start+timedelta(hours=1) for slot in busy)
            routine.rrule = 'invalid'
            await session.flush()
            with pytest.raises(HTTPException) as exc:
                await busy_for_window(session, owner, start, start+timedelta(days=1), ZoneInfo('UTC'))
            assert exc.value.status_code == 409
            routine.rrule = 'FREQ=DAILY;COUNT=3'
            task = Task(user_id=owner, title='Task')
            session.add(task)
            await session.commit()
            start = datetime.now(timezone.utc).replace(hour=20, minute=0, second=0, microsecond=0)+timedelta(days=2)
            block = await create_block(PlanBlockCreate(task_id=task.id, start_at=start,
                end_at=start+timedelta(hours=1)), session, owner)
            expected = start.astimezone(ZoneInfo('Asia/Kolkata')).replace(hour=0, minute=0).astimezone(timezone.utc)
            assert block['plan_date'].replace(tzinfo=timezone.utc) == expected
            moved = await patch_block(UUID(block['id']), PlanBlockPatch(start_at=start+timedelta(days=1),
                end_at=start+timedelta(days=1, hours=1)), session, owner)
            assert moved['plan_date'].replace(tzinfo=timezone.utc) == expected+timedelta(days=1)
            task.status = 'done'
            await session.commit()
            done = await patch_block(UUID(block['id']), PlanBlockPatch(status='done'), session, owner)
            assert done['status'] == 'done'
        await engine.dispose()
    asyncio.run(run())
