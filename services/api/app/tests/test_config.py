import pytest

from app.core.config import Settings, get_settings


def test_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.database_url is None
    assert settings.api_v1_prefix == "/api/v1"


def test_environment_variables_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    settings = Settings(_env_file=None)
    assert settings.environment == "production"
    assert settings.log_level == "WARNING"


def test_invalid_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging-typo")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_cors_origin_list_parsing() -> None:
    settings = Settings(_env_file=None, cors_origins="http://localhost:3000, http://admin.local")
    assert settings.cors_origin_list == ["http://localhost:3000", "http://admin.local"]
    assert Settings(_env_file=None, cors_origins="").cors_origin_list == []


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
