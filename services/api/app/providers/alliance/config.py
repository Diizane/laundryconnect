"""Alliance connector mode resolution and live-access gating."""

import os
from enum import StrEnum
from pathlib import Path

from app.core.config import Settings
from app.providers.errors import LiveModeRefused

# Nearest ancestor containing .git — used to refuse session files inside the
# repository. Falls back to the service root if no .git is found.
_HERE = Path(__file__).resolve()


class AllianceMode(StrEnum):
    FIXTURE = "fixture"
    SESSION = "session"
    CREDENTIAL = "credential"


def is_ci() -> bool:
    """Whether we are running in CI. GitHub Actions sets CI=true."""
    return os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_mode(settings: Settings) -> AllianceMode:
    """Parse the configured mode; unknown values fall back to fixture."""
    try:
        return AllianceMode(settings.alliance_mode.strip().lower())
    except ValueError:
        return AllianceMode.FIXTURE


def require_live_allowed(settings: Settings) -> None:
    """Raise LiveModeRefused unless live provider access is permitted.

    Independent guards, all must pass:
    - the kill switch must be off (safeguard 11/12);
    - never in CI (CI must not make live provider requests);
    - the access decision record must be approved (alliance_access_approved).
    """
    if settings.alliance_live_kill_switch:
        raise LiveModeRefused("Alliance live mode is disabled by the kill switch")
    if is_ci():
        raise LiveModeRefused("CI must not enter live provider mode")
    if not settings.alliance_access_approved:
        raise LiveModeRefused("Alliance access is not approved in the access decision record")


def find_repo_root() -> Path:
    for parent in (_HERE, *_HERE.parents):
        if (parent / ".git").exists():
            return parent
    # services/api is _HERE.parents[3]; use it as a conservative fallback.
    return _HERE.parents[3]


def assert_path_outside_repo(path: Path) -> Path:
    """Return the resolved path, or raise if it is inside the repository.

    Session files hold authentication material and must never live in the
    working tree where they could be committed.
    """
    resolved = path.expanduser().resolve()
    repo_root = find_repo_root()
    if resolved == repo_root or repo_root in resolved.parents:
        raise ValueError(
            "Refusing a session path inside the repository; choose a location "
            "outside the project working tree."
        )
    return resolved
