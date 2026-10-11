from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import get_settings

EMBEDDING_DIM = 768


class Base(DeclarativeBase):
    pass


def _engine():
    return create_async_engine(get_settings().postgres_dsn, pool_pre_ping=True)


engine = _engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
