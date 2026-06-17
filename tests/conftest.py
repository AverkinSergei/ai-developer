import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.clients.fakes import FakeBitrix, FakeGitLab, FakeGraph, FakeLLM

TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://ai_developer:ai_developer@localhost:5432/ai_developer",
)


@pytest.fixture
def bitrix() -> FakeBitrix:
    return FakeBitrix()


@pytest.fixture
def gitlab() -> FakeGitLab:
    return FakeGitLab()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def graph() -> FakeGraph:
    return FakeGraph()


@pytest_asyncio.fixture
async def db_session():
    """Сессия на реальном Postgres. Каждый тест — в транзакции с откатом."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        conn = await engine.connect()
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"Postgres недоступен: {exc}")
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()
