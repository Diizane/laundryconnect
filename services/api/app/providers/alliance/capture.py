"""Fixture sanitisation for recorded Alliance responses (operator-run).

After a manual login and capturing representative responses, run the raw
capture through `sanitise_capture` before writing a fixture. It strips
credential and session material — Cookie / Set-Cookie / Authorization
headers, tokens, usernames, account identifiers, signed-URL query strings,
and session ids — so nothing sensitive is ever committed.

Sanitisation is not a substitute for human review: a person must read the
resulting fixture diff before committing (enforced by
`test_alliance_fixtures_reviewed`, which requires a `_meta.reviewed_by`).
"""

import re
from typing import Any

# Header names removed entirely (case-insensitive).
_SENSITIVE_HEADERS = {
    "cookie",
    "set-cookie",
    "authorization",
    "x-auth-token",
    "x-session-id",
    "sid",
}
# Object keys whose values are redacted wherever they appear.
_SENSITIVE_KEYS = re.compile(
    r"(token|password|secret|cookie|session|authorization|username|"
    r"user_?name|email|account(_?id)?|api_?key)",
    re.IGNORECASE,
)
# Signed-URL / session query parameters stripped from URLs.
_SENSITIVE_QUERY = re.compile(
    r"([?&])(sig|signature|token|sid|session|expires|key|auth)=[^&]*",
    re.IGNORECASE,
)

_REDACTED = "[REDACTED]"


def _strip_url(url: str) -> str:
    return _SENSITIVE_QUERY.sub(r"\1\2=" + _REDACTED, url)


def sanitise_capture(value: Any) -> Any:
    """Recursively redact credential/session material from a captured value."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_HEADERS:
                continue  # drop sensitive headers entirely
            if isinstance(key, str) and _SENSITIVE_KEYS.search(key):
                cleaned[key] = _REDACTED
            else:
                cleaned[key] = sanitise_capture(item)
        return cleaned
    if isinstance(value, list):
        return [sanitise_capture(item) for item in value]
    if isinstance(value, str) and ("http://" in value or "https://" in value):
        return _strip_url(value)
    return value
