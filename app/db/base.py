"""Async-движок БД и менеджер сессий."""

import contextlib
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, url: str) -> None:
        self._engine = create_async_engine(url, pool_pre_ping=True)
        self._sessionmaker = async_sessionmaker(bind=self._engine, expire_on_commit=False)

    async def close(self) -> None:
        if self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        async with self._engine.begin() as connection:
            yield connection

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        session = self._sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # Используется в тестах для создания/удаления схемы.
    async def create_all(self, connection: AsyncConnection) -> None:
        await connection.run_sync(Base.metadata.create_all)

    async def drop_all(self, connection: AsyncConnection) -> None:
        await connection.run_sync(Base.metadata.drop_all)


sessionmanager = DatabaseSessionManager()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with sessionmanager.session() as session:
        yield session
