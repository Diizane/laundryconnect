"""Security guarantees for the Alliance connector (required by M8 spec)."""

import json
import logging
from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.alliance.config import find_repo_root
from app.providers.alliance.connector import AllianceConnector
from app.providers.errors import LiveModeRefused
from app.providers.models import ProviderSearchStatus, QueryType
from app.providers.registry import ProviderRegistry

FUTURE = 4_102_444_800.0
PAST = 1_000_000.0
_SECRET_MARKERS = ("password", "cookie", "token", "authorization", "session", "secret")


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"_env_file": None}
    base.update(overrides)
    return Settings(**base)


def _write_state(path: Path, expires: float) -> str:
    path.write_text(json.dumps({"cookies": [{"name": "a", "value": "v", "expires": expires}]}))
    return str(path)


# 1. repr and logs contain no credentials/cookies/tokens/session state.
def test_connector_repr_has_no_secret_material() -> None:
    connector = AllianceConnector(settings=_settings(alliance_mode="session"))
    text = repr(connector).lower()
    for marker in _SECRET_MARKERS:
        assert f"{marker}=" not in text and f"{marker}:" not in text
    # repr should also never embed a filesystem path.
    assert "/" not in repr(connector)


async def test_session_logging_emits_no_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {"cookies": [{"name": "auth", "value": "super-secret-value", "expires": FUTURE}]}
        )
    )
    connector = AllianceConnector(
        settings=_settings(alliance_mode="session", alliance_session_path=str(path))
    )
    with caplog.at_level(logging.DEBUG):
        # Loads the session and logs a cookie COUNT, never values.
        await connector.health_check()
    assert "super-secret-value" not in caplog.text
    for marker in ('"value"', "cookie="):
        assert marker not in caplog.text


# 2. CI cannot enter live mode.
async def test_ci_cannot_enter_live_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    path = _write_state(tmp_path / "valid.json", FUTURE)  # a VALID session
    connector = AllianceConnector(
        settings=_settings(
            alliance_mode="session",
            alliance_session_path=path,
            alliance_access_approved=True,  # even with access approved…
        )
    )
    # …CI must still refuse a live request (session is valid, so we reach the gate).
    with pytest.raises(LiveModeRefused, match="CI"):
        await connector.search("SC60", QueryType.AUTO)


async def test_live_refused_when_access_not_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    path = _write_state(tmp_path / "valid.json", FUTURE)
    connector = AllianceConnector(
        settings=_settings(
            alliance_mode="session",
            alliance_session_path=path,
            alliance_access_approved=False,  # record is UNKNOWN
        )
    )
    with pytest.raises(LiveModeRefused, match="not approved"):
        await connector.search("SC60", QueryType.AUTO)


# 3. Session files inside the repository are rejected.
async def test_session_path_inside_repo_is_rejected() -> None:
    inside = str(find_repo_root() / "alliance-session.json")
    connector = AllianceConnector(
        settings=_settings(alliance_mode="session", alliance_session_path=inside)
    )
    # Repo-path session is treated as invalid → reauthentication required,
    # never loaded from the working tree.
    registry = ProviderRegistry()
    registry.register(connector)
    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5)
    [outcome] = aggregated.providers
    assert outcome.status == ProviderSearchStatus.REAUTH_REQUIRED


# 4. Expired sessions return reauthentication_required (via the registry).
async def test_expired_session_reports_reauth_required(tmp_path: Path) -> None:
    path = _write_state(tmp_path / "expired.json", PAST)
    connector = AllianceConnector(
        settings=_settings(alliance_mode="session", alliance_session_path=path)
    )
    registry = ProviderRegistry()
    registry.register(connector)
    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5)
    [outcome] = aggregated.providers
    assert outcome.status == ProviderSearchStatus.REAUTH_REQUIRED
    assert outcome.error == "SessionExpired"
    # The outcome must not leak any session detail beyond the class name.
    assert "expired.json" not in aggregated.model_dump_json()


async def test_missing_session_reports_reauth_required() -> None:
    connector = AllianceConnector(
        settings=_settings(alliance_mode="session", alliance_session_path=None)
    )
    registry = ProviderRegistry()
    registry.register(connector)
    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5)
    [outcome] = aggregated.providers
    assert outcome.status == ProviderSearchStatus.REAUTH_REQUIRED


# 5. Credential mode is refused (terms do not permit it).
async def test_credential_mode_is_refused() -> None:
    connector = AllianceConnector(settings=_settings(alliance_mode="credential"))
    with pytest.raises(LiveModeRefused, match="credential"):
        await connector.search("SC60", QueryType.AUTO)
