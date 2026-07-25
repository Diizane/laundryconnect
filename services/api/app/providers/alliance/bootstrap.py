"""Manual session bootstrap (operator-run, local only).

Opens a VISIBLE browser so a human operator logs in and completes any
MFA/CAPTCHA themselves, then saves the authenticated storage state to a
local path OUTSIDE the repository with restrictive permissions.

This tool is never run by CI or the service. It requires the optional
`bootstrap` dependency group (Playwright) and a one-time browser install:

    uv pip install -e ".[bootstrap]"
    playwright install chromium
    ALLIANCE_SESSION_PATH=~/.laundryconnect/alliance-session.json \\
        python -m app.providers.alliance.bootstrap

It never prints cookies, tokens, credentials, page HTML, or the storage
state. It must not be used to bypass bot protection — a human performs the
login. Do not run it until the access decision record is approved or
conditionally approved.
"""

import logging
import os
import sys
from pathlib import Path

from app.providers.alliance.config import assert_path_outside_repo
from app.providers.alliance.session import secure_session_file

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://portal.alliancels.net/s/login/"
# Parts Connection: authenticated search/parts host. Visiting it in the same
# logged-in context captures its cookies into the saved session so the
# connector can reach it. The operator confirms it loaded before saving.
_PARTS_URL = "https://pc.alliancels.net/en/Search/StartsWith?searchString=SC60&x.Show=Assembly"


def bootstrap(session_path: str) -> None:
    target = assert_path_outside_repo(Path(session_path))
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - optional dependency
        raise SystemExit(
            "Playwright is not installed. Run: uv pip install -e '.[bootstrap]' "
            "&& playwright install chromium"
        ) from None

    print(  # noqa: T201 - operator UX, prints no sensitive data
        "Opening a browser. Log in manually and complete any MFA/CAPTCHA, "
        "then return here and press Enter."
    )
    with sync_playwright() as playwright:  # pragma: no cover - requires a browser + human
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(_LOGIN_URL)
        input("Press Enter once you have finished logging in… ")
        # Visit Parts Connection so its cookies are captured too. If it shows
        # a search page you are authenticated there; if it asks you to log in,
        # do so, then continue.
        print("Opening Parts Connection to capture its session…")  # noqa: T201
        page.goto(_PARTS_URL)
        input("Press Enter once the Parts Connection page has loaded… ")
        # storage_state writes cookies/localStorage for ALL visited hosts to
        # disk; we never read or print its contents here.
        context.storage_state(path=str(target))
        browser.close()

    secure_session_file(target)
    print(f"Session saved to {target} (permissions restricted).")  # noqa: T201


def main(argv: list[str] | None = None) -> int:
    session_path = os.environ.get("ALLIANCE_SESSION_PATH")
    if not session_path:
        print(  # noqa: T201
            "Set ALLIANCE_SESSION_PATH to a file OUTSIDE the repository, e.g. "
            "~/.laundryconnect/alliance-session.json",
            file=sys.stderr,
        )
        return 2
    try:
        bootstrap(session_path)
    except ValueError as exc:
        print(f"Refused: {exc}", file=sys.stderr)  # noqa: T201
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
