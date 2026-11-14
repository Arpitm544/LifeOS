import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base, Conflict, Event, PlanBlock, Preference, Task
from app.services.planning_service import rebuild_plan


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


def test_rebuild_uses_persisted_calendar_preferences_and_capacity():
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        owner = uuid4()
        now = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)
        async with factory() as session:
            session.add_all([
                Preference(user_id=owner, key='timezone', value={'name': 'UTC'}),
                Preference(user_id=owner, key='work_hours', value={'start': '09:00', 'end': '12:00'}),
                Event(user_id=owner, title='Meeting', start_at=now + timedelta(hours=2),
                    end_at=now + timedelta(hours=3), source='manual'),
                Task(user_id=owner, title='Urgent', deadline_at=now + timedelta(hours=4),
                    effort_est_min=120, importance=5, created_at=now),
                Task(user_id=owner, title='Too much', deadline_at=now + timedelta(hours=4),
                    effort_est_min=120, importance=1, created_at=now),
            ])
            await session.commit()
            result = await rebuild_plan(session, owner, now=now, days=1)
            await session.commit()
            blocks = (await session.execute(select(PlanBlock))).scalars().all()
            # Meeting buffers leave only 100 minutes of the 09:00–12:00 work window.
            assert sum(int((block.end_at - block.start_at).total_seconds() / 60) for block in blocks) == 100
            assert all(block.end_at <= now + timedelta(hours=4) for block in blocks)
            assert result['unplaced_task_ids']
            assert (await session.execute(select(Conflict))).scalars().all()
        await engine.dispose()
    asyncio.run(run())
