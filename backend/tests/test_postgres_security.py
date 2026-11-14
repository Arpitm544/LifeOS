"""Opt-in on a migrated disposable Supabase database; all inserted rows roll back."""
import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from app.database_tls import database_ssl_context


@pytest.mark.skipif(os.getenv('RUN_POSTGRES_TESTS') != '1' or not os.getenv('TEST_DATABASE_URL'),
                    reason='Requires explicit opt-in and migrated disposable PostgreSQL database')
def test_actual_rls_and_owned_foreign_keys():
    async def run():
        url = os.environ['TEST_DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://', 1)
        connection = await asyncpg.connect(url, ssl=database_ssl_context(), timeout=15)
        transaction = connection.transaction()
        await transaction.start()
        try:
            alice, bob = 'user_test_alice', 'user_test_bob'
            ta, tb = uuid4(), uuid4()
            for owner in (alice, bob):
                await connection.execute('INSERT INTO public.users(id) VALUES($1)', owner)
            for owner, task in ((alice, ta), (bob, tb)):
                await connection.execute("INSERT INTO public.tasks(id,user_id,title) VALUES($1,$2,'RLS fixture')", task, owner)
            await connection.execute('SET LOCAL ROLE lifeos_api')
            await connection.execute("SELECT set_config('request.jwt.claim.sub',$1,true)", alice)
            rows = await connection.fetch('SELECT id FROM public.tasks')
            assert {row['id'] for row in rows} == {ta}
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.execute("INSERT INTO public.tasks(user_id,title) VALUES($1,'Wrong owner')", bob)
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                async with connection.transaction():
                    await connection.execute('INSERT INTO public.plan_blocks(user_id,task_id,start_at,end_at,plan_date) VALUES($1,$2,now(),now()+interval \'1 hour\',now())', alice, tb)
            await connection.execute("SELECT set_config('request.jwt.claim.sub',$1,true)", bob)
            assert await connection.fetchval('SELECT count(*) FROM public.tasks WHERE id=$1', ta) == 0
            assert await connection.fetchval('SELECT count(*) FROM public.tasks WHERE id=$1', tb) == 1
        finally:
            await transaction.rollback()
            await connection.close()
    asyncio.run(run())
