# templates/tests/conftest.py — Shared Test Fixtures
# To modify: edit THIS file directly, then run: python3 orchestrate.py generate
#
# PHASE 9 | Docs: https://fastapi.tiangolo.com/tutorial/testing/

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app import get_session, app, Base


# --- Test database URL ---
# Option A: In-memory SQLite (fast, simple, less realistic)
#   TEST_DATABASE_URL = "sqlite+aiosqlite://"
# Option B: Separate PostgreSQL (realistic, needs running container)
#   TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test_taskdb"
TEST_DATABASE_URL = "sqlite+aiosqlite://"


# Docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
test_engine = create_async_engine(TEST_DATABASE_URL, echo=True)
test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test, drop them after."""
    # Docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#synopsis-orm
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Provide a test database session that rolls back after each test."""
    # Docs: https://docs.pytest.org/en/stable/how-to/fixtures.html
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """
    Provide an async HTTP client pointing at the test app.
    Overrides the real DB session with the test session.
    Docs: https://fastapi.tiangolo.com/advanced/async-tests/
    """

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_task(client: AsyncClient) -> dict:
    """Create a sample task for tests that need an existing task."""
    response = await client.post(
        "/api/v1/tasks/",
        json={"title": "Test Task", "description": "A test task"},
    )
    assert response.status_code == 201
    return response.json()
