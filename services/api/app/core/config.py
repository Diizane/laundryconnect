"""Application configuration.

All configuration comes from environment variables (or a `.env` file in local
development). Secrets must never be hardcoded here or committed to the
repository — see docs/SECURITY.md.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LaundryConnect API"
    environment: Environment = "development"
    debug: bool = False
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"

    # Database connection for Milestone 4 (PostgreSQL via SQLAlchemy).
    # Optional for now: the app must start without a database so the
    # foundation can run and be tested standalone.
    database_url: str | None = None

    # Comma-separated list of allowed CORS origins (admin portal, dev tools).
    cors_origins: str = ""

    # Comma-separated provider connector ids to enable (see
    # app/providers/registry.py). Only the mock connector exists so far;
    # production must configure this explicitly once real connectors land.
    enabled_providers: str = "mock"

    # Per-provider search timeout: a slow provider delays a search response
    # by at most this long and is then reported as timed_out.
    provider_timeout_seconds: float = 10.0

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @property
    def enabled_provider_list(self) -> list[str]:
        return _split_csv(self.enabled_providers)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    Cached so every module sees the same instance; tests can clear the cache
    (`get_settings.cache_clear()`) to inject different environments.
    """
    return Settings()
