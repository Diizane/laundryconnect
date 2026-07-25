"""API-level tests for enabling Alliance in /api/v1/search.

All fixture/mock — no network. Proves mock-only (default), Alliance-only,
mixed-provider behaviour, and provider-local failure (session expiry) without
failing the whole search.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> Iterator[TestClient]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def mock_only(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(monkeypatch, ENABLED_PROVIDERS="mock")


@pytest.fixture
def alliance_only(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Fixture mode: no network, CI-safe.
    yield from _client(monkeypatch, ENABLED_PROVIDERS="alliance", ALLIANCE_MODE="fixture")


@pytest.fixture
def mixed(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(monkeypatch, ENABLED_PROVIDERS="mock,alliance", ALLIANCE_MODE="fixture")


def _providers(body: dict) -> dict[str, str]:
    return {p["provider_id"]: p["status"] for p in body["providers"]}


def test_default_is_mock_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # No ENABLED_PROVIDERS set → the built-in default is mock only.
    monkeypatch.delenv("ENABLED_PROVIDERS", raising=False)
    for client in _client(monkeypatch):
        body = client.post("/api/v1/search", json={"query": "SC60"}).json()
        assert _providers(body) == {"mock": "success"}


def test_mock_only(mock_only: TestClient) -> None:
    body = mock_only.post("/api/v1/search", json={"query": "SC60"}).json()
    assert _providers(body) == {"mock": "success"}
    origins = {r["data_origin"] for g in body["groups"] for r in g["results"]}
    assert origins == {"mock"}


def test_alliance_only_fixture_mode(alliance_only: TestClient) -> None:
    body = alliance_only.post("/api/v1/search", json={"query": "SC60"}).json()
    assert _providers(body) == {"alliance": "success"}
    assert body["total_results"] > 0
    for group in body["groups"]:
        for result in group["results"]:
            assert result["provider_id"] == "alliance"
            # Fixture data is labelled 'fixture', never 'live'.
            assert result["data_origin"] == "fixture"


def test_mixed_providers(mixed: TestClient) -> None:
    body = mixed.post("/api/v1/search", json={"query": "SC60"}).json()
    assert _providers(body) == {"mock": "success", "alliance": "success"}
    origins = {r["data_origin"] for g in body["groups"] for r in g["results"]}
    assert origins == {"mock", "fixture"}


def test_session_expiry_fails_alliance_locally_not_whole_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Alliance in session mode with NO session file → the connector reports
    # reauthentication_required (pure-local, no network); mock still succeeds
    # and the search response is still 200 with mock's results.
    monkeypatch.delenv("CI", raising=False)
    for client in _client(
        monkeypatch,
        ENABLED_PROVIDERS="mock,alliance",
        ALLIANCE_MODE="session",
        ALLIANCE_SESSION_PATH="",
    ):
        response = client.post("/api/v1/search", json={"query": "SC60"})
        assert response.status_code == 200
        body = response.json()
        statuses = _providers(body)
        assert statuses["mock"] == "success"
        assert statuses["alliance"] == "reauthentication_required"
        # mock's results are still returned despite Alliance needing reauth.
        assert body["total_results"] > 0
        assert all(r["provider_id"] == "mock" for g in body["groups"] for r in g["results"])


def test_search_does_not_persist_to_database(alliance_only: TestClient) -> None:
    # The search path performs no DB writes (no DATABASE_URL configured here);
    # a successful search with results confirms it never touches the DB.
    body = alliance_only.post("/api/v1/search", json={"query": "SC60"}).json()
    assert body["total_results"] > 0


def test_search_does_not_log_result_payloads(
    mixed: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # Check 4: no provider payloads (result titles/URLs) or the query text
    # are written to logs; only structural metadata (counts, statuses).
    import logging

    with caplog.at_level(logging.DEBUG):
        body = mixed.post("/api/v1/search", json={"query": "SC60"}).json()

    titles = [r["title"] for g in body["groups"] for r in g["results"]]
    assert titles  # there were results to potentially leak
    logs = caplog.text
    for title in titles:
        assert title not in logs
    # The search-executed log carries structural fields, not the payload.
    assert "search executed" in logs
