from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.exceptions import AppError

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction_scope(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    try:
        yield session
        await session.commit()
    except AppError as exc:
        if exc.commit_on_error:
            await session.commit()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session, transaction_scope(session) as scoped:
        yield scoped


# "function" scope commits before the response is sent, not after.
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
