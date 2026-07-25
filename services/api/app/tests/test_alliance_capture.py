"""Fixture sanitiser: credential/session material is stripped before commit."""

from app.providers.alliance.capture import sanitise_capture


def test_sensitive_headers_dropped() -> None:
    cleaned = sanitise_capture(
        {"headers": {"Cookie": "sid=abc", "Set-Cookie": "x", "Accept": "application/json"}}
    )
    assert cleaned["headers"] == {"Accept": "application/json"}


def test_sensitive_keys_redacted() -> None:
    cleaned = sanitise_capture(
        {"username": "jsmith", "sessionId": "abc123", "account_id": "999", "title": "SC60"}
    )
    assert cleaned["username"] == "[REDACTED]"
    assert cleaned["sessionId"] == "[REDACTED]"
    assert cleaned["account_id"] == "[REDACTED]"
    assert cleaned["title"] == "SC60"


def test_signed_url_query_stripped() -> None:
    cleaned = sanitise_capture(
        {"url": "https://portal.alliancels.net/doc?sig=deadbeef&token=xyz&id=SC60"}
    )
    assert "deadbeef" not in cleaned["url"]
    assert "xyz" not in cleaned["url"]
    assert "sig=[REDACTED]" in cleaned["url"]


def test_nested_structures_sanitised() -> None:
    cleaned = sanitise_capture(
        {"results": [{"title": "SC60", "authorization": "Bearer tok"}, {"password": "p"}]}
    )
    assert cleaned["results"][0]["title"] == "SC60"
    # "authorization" is a sensitive header name → dropped entirely.
    assert "authorization" not in cleaned["results"][0]
    # "password" is a sensitive key → redacted in place.
    assert cleaned["results"][1]["password"] == "[REDACTED]"


def test_non_sensitive_values_untouched() -> None:
    original = {"model": "SC60", "pages": 42, "ok": True, "tags": ["service", "parts"]}
    assert sanitise_capture(original) == original


def test_sanitised_output_has_no_secret_markers() -> None:
    dirty = {
        "Set-Cookie": "sid=abc",
        "user": {"username": "jsmith", "email": "j@example.com"},
        "url": "https://x/y?token=secrettoken",
    }
    text = str(sanitise_capture(dirty)).lower()
    assert "jsmith" not in text
    assert "j@example.com" not in text
    assert "secrettoken" not in text
    assert "sid=abc" not in text
