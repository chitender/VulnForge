import os

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import audit_log, finding, image, merge_request, registry, scan, user  # noqa: F401
from app.models.base import Base

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
_SYNC_TEST_URL = _TEST_DB_URL.replace("+asyncpg", "+psycopg2") if _TEST_DB_URL else ""


def _get_sync_url() -> str:
    if _SYNC_TEST_URL:
        return _SYNC_TEST_URL
    from testcontainers.postgres import PostgresContainer

    if not hasattr(_get_sync_url, "_container"):
        _get_sync_url._container = PostgresContainer("postgres:16-alpine")
        _get_sync_url._container.start()
    return _get_sync_url._container.get_connection_url()


# ── Sync fixtures (schema/model tests) ─────────────────────────────────────


@pytest.fixture(scope="session")
def sync_db_engine():
    url = _get_sync_url()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sync_db(sync_db_engine) -> Session:
    SessionLocal = sessionmaker(sync_db_engine)
    with SessionLocal() as session:
        yield session
        session.rollback()


# ── Async fixtures (service tests) ─────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def async_db_engine():
    if not _TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set; async DB tests require it")
    engine = create_async_engine(_TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(async_db_engine) -> AsyncSession:
    """Async session for service-layer tests."""
    session_factory = async_sessionmaker(async_db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# ── Shared test data ────────────────────────────────────────────────────────

TEST_OWNER_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(scope="session")
async def test_user(async_db_engine):
    """Insert a single test user once per session; skip if already exists."""

    from sqlalchemy import text

    session_factory = async_sessionmaker(async_db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, keycloak_sub, email, name, role) "
                "VALUES (:id, :sub, :email, :name, 'VIEWER') "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": TEST_OWNER_ID,
                "sub": "test-keycloak-sub",
                "email": "test@patchpilot.test",
                "name": "Test User",
            },
        )
        await session.commit()
    return TEST_OWNER_ID
