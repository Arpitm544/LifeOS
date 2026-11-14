"""Local database workflow tests; SQLite does not validate PostgreSQL RLS/locks."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base, Task, ActionLog, Reminder
from app.schemas import TaskCreate
from app.services.task_service import create_task
from app.services.domain_service import audit, snapshot, undo_logged_action, replace_dependencies


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


def test_create_edit_undo_reminders_and_dependency_cycle():
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        owner = uuid4()
        async with factory() as session:
            task = await create_task(session, owner, TaskCreate(title='Report',
                deadline_at=datetime.now(timezone.utc) + timedelta(days=3)))
            other = await create_task(session, owner, TaskCreate(title='Quiz'))
            await session.commit()
            before = snapshot(task)
            task.title = 'Revised report'
            log = await audit(session, owner, task, before, 'update')
            await session.commit()
            await undo_logged_action(session, owner, log.id)
            await session.commit()
            assert task.title == 'Report'
            pending = (await session.execute(select(Reminder).where(Reminder.status == 'pending'))).scalars().all()
            assert len(pending) == 3
            await replace_dependencies(session, owner, task, [other.id])
            assert task.status == 'blocked'
            with pytest.raises(HTTPException) as error:
                await replace_dependencies(session, owner, other, [task.id])
            assert error.value.status_code == 409
            await session.rollback()
            # Confirm stale-state, expiry and ownership protections using real SQL.
            task = (await session.execute(select(Task).where(Task.title == 'Report'))).scalar_one()
            before = snapshot(task)
            task.title = 'Another edit'
            action = await audit(session, owner, task, before, 'update')
            await session.commit()
            with pytest.raises(HTTPException) as wrong_owner:
                await undo_logged_action(session, uuid4(), action.id)
            assert wrong_owner.value.status_code == 404
            task.title = 'Later edit'
            await session.commit()
            with pytest.raises(HTTPException) as stale:
                await undo_logged_action(session, owner, action.id)
            assert stale.value.status_code == 409
            action.created_at = datetime.now(timezone.utc) - timedelta(seconds=11)
            await session.commit()
            with pytest.raises(HTTPException) as expired:
                await undo_logged_action(session, owner, action.id)
            assert expired.value.status_code == 409
        await engine.dispose()
    asyncio.run(run())
