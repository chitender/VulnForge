import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.models.base import Base
from app.models import user, registry, image, scan, finding, merge_request, audit_log  # noqa: F401

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
# Convert asyncpg URL to psycopg2 for sync test fixtures
_SYNC_TEST_URL = _TEST_DB_URL.replace("+asyncpg", "+psycopg2") if _TEST_DB_URL else ""


def _get_sync_url() -> str:
    if _SYNC_TEST_URL:
        return _SYNC_TEST_URL
    # CI path: spin up a throwaway Postgres via testcontainers
    from testcontainers.postgres import PostgresContainer

    # Store container on module so it stays alive for session scope
    if not hasattr(_get_sync_url, "_container"):
        _get_sync_url._container = PostgresContainer("postgres:16-alpine")
        _get_sync_url._container.start()
    return _get_sync_url._container.get_connection_url()


@pytest.fixture(scope="session")
def sync_db_engine():
    url = _get_sync_url()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(sync_db_engine) -> Session:
    SessionLocal = sessionmaker(sync_db_engine)
    with SessionLocal() as session:
        yield session
        session.rollback()
