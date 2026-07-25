"""Authenticated browser session loading and validation.

Pure-local: reads and validates a Playwright storage-state file. Never makes
a network request and NEVER prints or returns cookie values, tokens, or any
session contents — only non-sensitive structural metadata (counts, the
earliest cookie expiry). Detects missing / invalid / expired sessions and
raises the typed reauthentication errors the connector maps to a structured
`reauthentication_required` outcome.
"""

import json
import logging
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from app.providers.alliance.config import assert_path_outside_repo
from app.providers.errors import SessionExpired, SessionInvalid, SessionMissing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionMetadata:
    """Non-sensitive facts about a loaded session. Deliberately excludes
    cookie values, tokens, and origins so it is safe to log."""

    cookie_count: int
    earliest_expiry_epoch: float | None


def _validate_storage_state(data: object) -> list[dict]:
    """Validate the Playwright storage-state shape; return the cookies list.

    Raises SessionInvalid (not the raw parser error) on any structural
    problem so no file contents leak through an exception message.
    """
    if not isinstance(data, dict):
        raise SessionInvalid("storage state is not an object")
    cookies = data.get("cookies")
    if not isinstance(cookies, list):
        raise SessionInvalid("storage state has no cookies list")
    for cookie in cookies:
        if not isinstance(cookie, dict) or "expires" not in cookie:
            raise SessionInvalid("storage state cookie is malformed")
    return cookies


def load_session(session_path: str | None, *, now: float | None = None) -> SessionMetadata:
    """Load and validate the session at `session_path`.

    Raises:
        SessionMissing   — no path configured, or file absent.
        SessionInvalid   — path inside the repo, unreadable, or wrong shape.
        SessionExpired   — every non-session cookie has expired.
    """
    if not session_path:
        raise SessionMissing("ALLIANCE_SESSION_PATH is not configured")

    try:
        resolved = assert_path_outside_repo(Path(session_path))
    except ValueError as exc:
        # Path-inside-repo is a configuration error, surfaced as invalid.
        raise SessionInvalid(str(exc)) from exc

    if not resolved.is_file():
        raise SessionMissing("no session file at the configured path")

    try:
        raw = resolved.read_text()
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # Never echo file contents; class name only.
        raise SessionInvalid(f"session file unreadable ({type(exc).__name__})") from exc

    cookies = _validate_storage_state(data)

    now = time.time() if now is None else now
    # Playwright uses expires == -1 for session cookies (no expiry). Consider
    # the session expired only when it has cookies and every cookie with a
    # real expiry is in the past and none are session cookies.
    real_expiries = [
        float(c["expires"])
        for c in cookies
        if isinstance(c.get("expires"), int | float) and c["expires"] > 0
    ]
    has_session_cookie = any(c.get("expires", 0) in (-1, 0) for c in cookies)
    if cookies and not has_session_cookie and real_expiries and max(real_expiries) <= now:
        raise SessionExpired("all session cookies have expired")

    earliest = min(real_expiries) if real_expiries else None
    metadata = SessionMetadata(cookie_count=len(cookies), earliest_expiry_epoch=earliest)
    logger.info(
        "alliance session loaded",
        extra={"cookie_count": metadata.cookie_count},  # no values, counts only
    )
    return metadata


def secure_session_file(path: Path) -> None:
    """Best-effort restrictive permissions (owner read/write only)."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:  # pragma: no cover - platform dependent
        logger.warning(
            "could not restrict session file permissions", extra={"error": type(exc).__name__}
        )
