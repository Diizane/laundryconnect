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

    # Shared API keys (comma-separated) protecting every non-health route.
    # REQUIRED in production — the app refuses to start without them, since
    # the backend holds an authenticated provider session. Generate with
    # `python -c "import secrets; print(secrets.token_urlsafe(32))"` and
    # store in the environment's secret manager. Empty in development/tests
    # disables auth.
    api_keys: str = ""

    # Comma-separated provider connector ids to enable (see
    # app/providers/registry.py). Only the mock connector exists so far;
    # production must configure this explicitly once real connectors land.
    enabled_providers: str = "mock"

    # Per-provider search timeout: a slow provider delays a search response
    # by at most this long and is then reported as timed_out.
    provider_timeout_seconds: float = 10.0

    # --- Alliance provider connector (Milestone 8) ---------------------------
    # Mode: "fixture" (default; recorded/synthetic data, no network, CI-safe),
    # "session" (human-bootstrapped browser session), or "credential"
    # (refused; automated credential login is not established as permitted).
    alliance_mode: str = "fixture"
    # Path to the operator's authenticated browser storage-state file. Must be
    # OUTSIDE the repository. Never committed; never logged.
    alliance_session_path: str | None = None
    # Master live gate — mirrors the access decision record. The record is
    # CONDITIONALLY APPROVED, but this stays FALSE by default so a live
    # request requires a deliberate per-environment opt-in after the
    # pre-first-request review. Live modes refuse unless this is true.
    alliance_access_approved: bool = False
    # Kill switch (safeguard 11/12): when true, live access is refused
    # immediately regardless of approval — flip this if Alliance objects.
    alliance_live_kill_switch: bool = False
    # Live-fetch controls (safeguards 7, 8). Conservative defaults.
    # Login is on portal.alliancels.net; parts/model search is on the Parts
    # Connection host pc.alliancels.net. Both are authorised (service partner).
    # Secret for opaque (authenticated-encrypted) document tokens (ADR
    # 0014). REQUIRED in production (min 32 chars) — document-token
    # operations refuse rather than silently using a process secret. When
    # empty in development/tests, an ephemeral per-process secret is used
    # (tokens then do not survive restarts). Rotating it invalidates all
    # outstanding tokens.
    document_token_secret: str = ""

    # --- Document cache (Milestone 12) --------------------------------------
    # Stores documents the operator is entitled to download so repeat opens
    # are instant and still work when the provider session has expired.
    # A revalidating cache, not an archive: every hit is checked against the
    # provider with If-None-Match/If-Modified-Since, and an unvalidated copy
    # is served ONLY when the provider cannot answer — labelled `cached`
    # with its age. OFF by default.
    document_cache_enabled: bool = False
    document_cache_path: str = "/var/cache/laundryconnect/documents"
    document_cache_max_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB
    # Longest a copy may be served without a successful revalidation. Manuals
    # get revised, and a superseded procedure is a safety problem, not just a
    # correctness one.
    document_cache_max_stale_seconds: int = 90 * 24 * 3600  # 90 days
    # Token lifetime: long enough for discover → tap → download, short
    # enough that a leaked token goes stale quickly.
    document_token_ttl_seconds: int = 900  # 15 minutes

    alliance_base_url: str = "https://portal.alliancels.net"
    # Parts Connection base — provider-relative document-workflow paths
    # (/en/Manual, /en/Model/Literature, /manuals/...) resolve against this.
    alliance_parts_base_url: str = "https://pc.alliancels.net"
    alliance_allowed_hosts: str = "portal.alliancels.net,pc.alliancels.net"
    # Full search URL templates ({query} is URL-encoded and substituted).
    # Model/keyword queries use the StartsWith model search; SERIAL queries
    # use the portal's dedicated BySerial endpoint, which resolves a machine
    # serial to its exact factory configuration (validated live 2026-07-30;
    # first field-test finding 2026-08-02: StartsWith on a serial returns
    # unrelated prefix-matched models).
    alliance_search_url: str = (
        "https://pc.alliancels.net/en/Search/StartsWith?searchString={query}&x.Show=Assembly"
    )
    alliance_serial_search_url: str = (
        "https://pc.alliancels.net/en/Search/BySerial?searchString={query}&x.Show=Assembly"
    )
    # Session keepalive (Milestone 11): periodically exercise an already
    # authorised session so it does not expire through inactivity, and
    # measure how long sessions actually live. Never logs in and never
    # touches credentials. OFF by default — explicit per-environment
    # opt-in, like every other live behaviour.
    alliance_keepalive_enabled: bool = False
    # Conservative: 96 requests/day at the default, far under the rate limit.
    alliance_keepalive_interval_seconds: int = 900  # 15 minutes
    # ONE fixed already-authorised page. Not a crawl target.
    alliance_keepalive_url: str = "https://pc.alliancels.net/"

    alliance_rate_limit_per_minute: float = 12.0
    alliance_request_timeout_seconds: float = 20.0
    alliance_max_retries: int = 2
    # Max concurrent live requests (single-flight; no internal fan-out).
    alliance_max_concurrency: int = 1
    # Longest a 429 Retry-After will be honoured before giving up.
    alliance_max_retry_after_seconds: float = 60.0
    # Download caps (safeguard: bounded memory / no unbounded transfers).
    alliance_max_response_bytes: int = 5 * 1024 * 1024  # search HTML/JSON: 5 MB
    alliance_max_document_bytes: int = 100 * 1024 * 1024  # PDF: 100 MB
    alliance_download_timeout_seconds: float = 60.0

    @property
    def alliance_allowed_host_list(self) -> list[str]:
        return _split_csv(self.alliance_allowed_hosts)

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @property
    def api_key_list(self) -> list[str]:
        return _split_csv(self.api_keys)

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
