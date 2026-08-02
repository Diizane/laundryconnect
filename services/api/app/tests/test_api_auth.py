"""API key authentication (Milestone 11) — offline."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.auth import InsecureConfiguration, validate_auth_configuration
from app.core.config import Settings, get_settings
from app.main import create_app

KEY = "test-key-that-is-long-enough-abcdefgh"
OTHER_KEY = "second-key-also-long-enough-12345678"


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
def secured(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(monkeypatch, API_KEYS=f"{KEY},{OTHER_KEY}", ENABLED_PROVIDERS="mock")


class TestStartupEnforcement:
    def test_production_without_keys_refuses_to_start(self) -> None:
        settings = Settings(_env_file=None, environment="production", api_keys="")
        with pytest.raises(InsecureConfiguration, match="API_KEYS"):
            validate_auth_configuration(settings)

    def test_production_with_short_key_refuses_to_start(self) -> None:
        settings = Settings(_env_file=None, environment="production", api_keys="short")
        with pytest.raises(InsecureConfiguration, match="at least"):
            validate_auth_configuration(settings)

    def test_production_with_strong_keys_starts(self) -> None:
        settings = Settings(_env_file=None, environment="production", api_keys=KEY)
        validate_auth_configuration(settings)  # no raise

    def test_development_without_keys_allowed(self) -> None:
        settings = Settings(_env_file=None, environment="development", api_keys="")
        validate_auth_configuration(settings)  # auth simply disabled


class TestRequestAuthentication:
    def test_search_without_key_is_401(self, secured: TestClient) -> None:
        response = secured.post("/api/v1/search", json={"query": "SC60"})
        assert response.status_code == 401

    def test_search_with_valid_key_succeeds(self, secured: TestClient) -> None:
        response = secured.post(
            "/api/v1/search", json={"query": "SC60"}, headers={"X-API-Key": KEY}
        )
        assert response.status_code == 200

    def test_second_configured_key_also_works(self, secured: TestClient) -> None:
        response = secured.post(
            "/api/v1/search", json={"query": "SC60"}, headers={"X-API-Key": OTHER_KEY}
        )
        assert response.status_code == 200

    def test_bearer_authorization_header_accepted(self, secured: TestClient) -> None:
        response = secured.post(
            "/api/v1/search",
            json={"query": "SC60"},
            headers={"Authorization": f"Bearer {KEY}"},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("value", ["", "wrong-key", KEY[:-1], KEY + "x", KEY.upper()])
    def test_invalid_keys_rejected(self, secured: TestClient, value: str) -> None:
        response = secured.post(
            "/api/v1/search", json={"query": "SC60"}, headers={"X-API-Key": value}
        )
        assert response.status_code == 401

    def test_document_endpoints_require_a_key(self, secured: TestClient) -> None:
        assert (
            secured.get("/api/v1/providers/mock/documents", params={"ref": "SC60"}).status_code
            == 401
        )
        assert secured.get("/api/v1/providers/mock/documents/sometoken").status_code == 401

    def test_health_endpoints_stay_open(self, secured: TestClient) -> None:
        # Load balancers and uptime checks must work without a key.
        assert secured.get("/api/v1/health/live").status_code == 200
        assert secured.get("/api/v1/health").status_code == 200

    def test_rejection_body_leaks_nothing(self, secured: TestClient) -> None:
        body = secured.post("/api/v1/search", json={"query": "SC60"}).text
        assert KEY not in body and OTHER_KEY not in body

    def test_supplied_key_never_appears_in_logs(
        self, secured: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.DEBUG):
            secured.post(
                "/api/v1/search", json={"query": "SC60"}, headers={"X-API-Key": "sekrit-attempt"}
            )
        assert "sekrit-attempt" not in caplog.text


class TestAuthDisabledByDefault:
    def test_no_keys_configured_leaves_api_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Existing local/CI behaviour is unchanged when API_KEYS is unset.
        for client in _client(monkeypatch, API_KEYS="", ENABLED_PROVIDERS="mock"):
            assert client.post("/api/v1/search", json={"query": "SC60"}).status_code == 200
