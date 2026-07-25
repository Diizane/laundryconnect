"""Alliance session lifecycle: validation, expiry, repo-path refusal."""

import json
from pathlib import Path

import pytest

from app.providers.alliance.config import assert_path_outside_repo, find_repo_root
from app.providers.alliance.session import load_session
from app.providers.errors import SessionExpired, SessionInvalid, SessionMissing

FUTURE = 4_102_444_800.0  # 2100-01-01
PAST = 1_000_000.0  # 1970


def _write_state(path: Path, cookies: list[dict]) -> None:
    path.write_text(json.dumps({"cookies": cookies, "origins": []}))


def test_missing_path_raises_session_missing() -> None:
    with pytest.raises(SessionMissing):
        load_session(None)


def test_absent_file_raises_session_missing(tmp_path: Path) -> None:
    with pytest.raises(SessionMissing):
        load_session(str(tmp_path / "nope.json"))


def test_invalid_json_raises_session_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("this is not json")
    with pytest.raises(SessionInvalid):
        load_session(str(bad))


def test_wrong_shape_raises_session_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "wrong.json"
    bad.write_text(json.dumps({"not": "storage state"}))
    with pytest.raises(SessionInvalid):
        load_session(str(bad))


def test_expired_cookies_raise_session_expired(tmp_path: Path) -> None:
    state = tmp_path / "expired.json"
    _write_state(state, [{"name": "auth", "value": "x", "expires": PAST}])
    with pytest.raises(SessionExpired):
        load_session(str(state))


def test_valid_future_session_loads(tmp_path: Path) -> None:
    state = tmp_path / "valid.json"
    _write_state(state, [{"name": "auth", "value": "x", "expires": FUTURE}])
    metadata = load_session(str(state))
    assert metadata.cookie_count == 1
    assert metadata.earliest_expiry_epoch == FUTURE


def test_session_cookie_without_expiry_is_not_expired(tmp_path: Path) -> None:
    state = tmp_path / "session-cookie.json"
    _write_state(state, [{"name": "auth", "value": "x", "expires": -1}])
    # A pure session cookie (expires == -1) is not treated as expired.
    assert load_session(str(state)).cookie_count == 1


def test_session_metadata_excludes_values(tmp_path: Path) -> None:
    state = tmp_path / "valid.json"
    _write_state(state, [{"name": "auth", "value": "super-secret-value", "expires": FUTURE}])
    metadata = load_session(str(state))
    # The returned metadata must not carry cookie values.
    assert "super-secret-value" not in repr(metadata)


def test_path_inside_repo_refused_by_guard() -> None:
    inside = find_repo_root() / "services" / "api" / "session.json"
    with pytest.raises(ValueError, match="inside the repository"):
        assert_path_outside_repo(inside)


def test_load_session_rejects_repo_path() -> None:
    inside = str(find_repo_root() / "alliance-session.json")
    # Refused as invalid (never loaded from inside the working tree).
    with pytest.raises(SessionInvalid):
        load_session(inside)
