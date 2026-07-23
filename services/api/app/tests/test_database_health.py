"""Readiness and session-dependency behaviour with and without a database."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import DbSessionDep
from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def db_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client whose app is configured with a working SQLite database."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/health.db")
    get_settings.cache_clear()
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_readiness_ok_with_configured_database(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == [{"name": "database", "status": "ok", "detail": None}]


def test_readiness_failed_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A database path inside a missing directory fails fast on connect.
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/no-such-dir/x.db")
    get_settings.cache_clear()
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/health/ready")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    [check] = body["checks"]
    assert check["status"] == "failed"
    # Failure detail is the exception class only — never a DSN or message.
    assert "no-such-dir" not in response.text


def test_db_session_dependency_503_when_unconfigured(client: TestClient) -> None:
    app = client.app

    @app.get("/api/v1/_db-check")
    async def db_check(session: DbSessionDep) -> dict[str, bool]:
        return {"ok": True}

    response = client.get("/api/v1/_db-check")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Database is not configured."


def test_db_session_dependency_works_when_configured(db_client: TestClient) -> None:
    app = db_client.app

    @app.get("/api/v1/_db-check")
    async def db_check(session: DbSessionDep) -> dict[str, bool]:
        from sqlalchemy import text

        await session.execute(text("SELECT 1"))
        return {"ok": True}

    response = db_client.get("/api/v1/_db-check")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
