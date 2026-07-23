from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.base import Base
from app.database.session import create_engine, create_session_factory
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A test client against a freshly built app in the test environment.

    DATABASE_URL is cleared so tests are deterministic regardless of any
    developer .env file; database-specific tests configure their own URL.
    """
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    app = create_app()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """A session against a fresh SQLite database with the full schema.

    SQLite keeps unit tests independent of a running PostgreSQL; dialect
    differences are accepted for now (see ADR 0005).
    """
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()
