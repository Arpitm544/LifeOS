from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from .config import get_settings
from .database_tls import database_ssl_context
from fastapi import Depends
from sqlalchemy import event, text, select
from sqlalchemy.orm import Session
from .auth import current_user_id
from .models import User


def apply_user_context(session, transaction, connection):
    owner = session.info.get('user_id')
    if owner is None:
        return  # Administrative scripts use a separate unscoped session.
    connection.execute(text('SET LOCAL ROLE lifeos_api'))
    connection.execute(text("SELECT set_config('request.jwt.claim.sub', :owner, true)"), {'owner': str(owner)})
    connection.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"),
                       {'claims': '{"sub":"' + str(owner) + '","role":"authenticated"}'})


event.listen(Session, 'after_begin', apply_user_context)

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True,
                             connect_args={"ssl": database_ssl_context()} if get_settings().database_ssl else {"ssl": False})
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def get_session(user_id=Depends(current_user_id)) -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        # after_begin reapplies SET LOCAL after endpoint commits and refreshes.
        session.info['user_id'] = user_id
        # Clerk owns identity. LifeOS keeps a minimal local row for tenant FKs;
        # profile synchronization can enrich it later without trusting client data.
        from sqlalchemy.dialects.postgresql import insert
        await session.execute(insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=['id']))
        yield session

