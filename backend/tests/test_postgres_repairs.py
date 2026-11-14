"""Run only against an isolated disposable PostgreSQL cluster; creates/drops databases."""
import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest

URL = os.getenv('REPAIR_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires isolated REPAIR_TEST_DATABASE_URL')
MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'


@pytest.mark.parametrize('legacy_rows', [False, True])
def test_migrations_shared_limits_bootstrap_and_concurrent_placement(monkeypatch, legacy_rows):
    import asyncpg
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app import db
    from app.models import Task, PlanBlock
    from app.rate_limit import PostgresWindowLimiter
    from app.api.plan_blocks import create_block
    from app.schemas_plan_blocks import PlanBlockCreate
    from fastapi import HTTPException
    from datetime import datetime, timedelta, timezone

    async def run():
        admin = await asyncpg.connect(URL, ssl=False)
        database = 'lifeos_repair_' + uuid4().hex
        # Never reuse or drop a pre-existing application role.
        assert not await admin.fetchval("select 1 from pg_roles where rolname='lifeos_api'"), 'Use an isolated cluster without lifeos_api'
        await admin.execute('create database ' + database)
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(URL)
        url = urlunsplit(parts._replace(path='/' + database))
        connection = await asyncpg.connect(url, ssl=False)
        engine = None
        try:
            await connection.execute('''create schema auth;
                create table auth.users(id uuid primary key);
                create function auth.uid() returns uuid language sql stable as $$
                  select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid
                $$;''')
            async def apply(number):
                path = next(MIGRATIONS.glob(f'{number:03d}_*.sql'))
                await connection.execute(path.read_text())
            await apply(1)
            await apply(2)
            # Reject a pre-provisioned role with unexpected schema grants.
            await connection.execute('create role lifeos_api nologin noinherit; grant create on schema public to lifeos_api')
            with pytest.raises(asyncpg.RaiseError, match='memberships, ownership or explicit grants'):
                await apply(3)
            await connection.execute('rollback; revoke create on schema public from lifeos_api; drop role lifeos_api')
            await apply(3)
            await apply(4)
            if legacy_rows:
                # Upgrade rows can exist in auth + tasks without a local users row.
                legacy, task_id = uuid4(), uuid4()
                await connection.execute('insert into auth.users values($1)', legacy)
                await connection.execute("insert into tasks(id,user_id,title) values($1,$2,'legacy task')", task_id, legacy)
                with pytest.raises(asyncpg.RaiseError, match='Missing legacy-to-Clerk mapping'):
                    await apply(5)
                await connection.execute('rollback')
                assert await connection.fetchval("select data_type from information_schema.columns where table_name='tasks' and column_name='user_id'") == 'uuid'
                await connection.execute('create temp table lifeos_identity_map(legacy_id uuid primary key, clerk_id text not null unique)')
                await connection.execute('insert into lifeos_identity_map values($1,$2)', legacy, 'user_mapped')
                await apply(5)
                assert await connection.fetchval('select user_id from tasks where id=$1', task_id) == 'user_mapped'
                assert await connection.fetchval("select id from public.users where id='user_mapped'") == 'user_mapped'
            else:
                await apply(5)
            # Reject unsafe memberships on already-provisioned installations too.
            await connection.execute('create role repair_extra nologin; grant repair_extra to lifeos_api')
            with pytest.raises(asyncpg.RaiseError, match='unexpected privileges'):
                await apply(6)
            await connection.execute('rollback; revoke repair_extra from lifeos_api; drop role repair_extra')
            await apply(6)
            assert await connection.fetchval("select count(*) from pg_policies where schemaname='public' and qual like '%auth.uid%'") == 0
            engine = create_async_engine(url.replace('postgresql://', 'postgresql+asyncpg://'), connect_args={'ssl': False})
            factory = async_sessionmaker(engine, expire_on_commit=False)
            monkeypatch.setattr(db, 'SessionFactory', factory)
            monkeypatch.setattr(db, 'engine', engine)
            owner = 'user_parallel'
            # Concurrent first requests use the real get_session and transaction context.
            async def bootstrap():
                async for session in db.get_session(owner):
                    await session.commit()
            await asyncio.gather(*(bootstrap() for _ in range(5)))
            assert await connection.fetchval('select count(*) from public.users where id=$1', owner) == 1
            # Separate limiter instances and database sessions share an atomic budget.
            results = await asyncio.gather(*(PostgresWindowLimiter().allow(identity=owner, bucket='chat', limit=3) for _ in range(12)))
            assert sum(allowed for allowed, _ in results) == 3
            await connection.execute("insert into rate_limit_events values('user_inactive','chat',now()-interval '2 minutes')")
            await PostgresWindowLimiter().allow(identity=owner, bucket='api', limit=300)
            assert await connection.fetchval("select count(*) from rate_limit_events where user_id='user_inactive'") == 0
            # Two different tasks cannot claim the same interval concurrently.
            async with factory() as session:
                tasks = [Task(user_id=owner, title='a'), Task(user_id=owner, title='b')]
                session.add_all(tasks)
                await session.commit()
                ids = [item.id for item in tasks]
            start = datetime.now(timezone.utc) + timedelta(days=1)
            async def place(task_id):
                async with factory() as session:
                    session.info['user_id'] = owner
                    try:
                        await create_block(PlanBlockCreate(task_id=task_id, start_at=start, end_at=start+timedelta(hours=1)), session, owner)
                        return 201
                    except HTTPException as exc:
                        await session.rollback()
                        return exc.status_code
            assert sorted(await asyncio.gather(*(place(identity) for identity in ids))) == [201, 409]
            # The restricted role cannot see another owner's data.
            async with factory() as session:
                session.info['user_id'] = owner
                assert not (await session.execute(select(Task).where(Task.user_id == 'user_mapped'))).scalars().all()
                from sqlalchemy.exc import DBAPIError
                with pytest.raises(DBAPIError):
                    session.add(Task(user_id='user_mapped', title='forbidden'))
                    await session.flush()
                await session.rollback()
            from seed_demo import build_demo, load_demo
            from datetime import date
            fixtures = build_demo('user_fresh_seed', date(2026, 11, 14))
            assert sum((await load_demo(fixtures)).values()) > 0
            assert sum((await load_demo(fixtures)).values()) == 0
            assert await connection.fetchval("select id from public.users where id='user_fresh_seed'") == 'user_fresh_seed'
        finally:
            if engine is not None:
                await engine.dispose()
            await connection.close()
            await admin.execute('drop database ' + database + ' with (force)')
            await admin.execute('drop role if exists lifeos_api')
            await admin.close()
    asyncio.run(run())
