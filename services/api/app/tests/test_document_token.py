"""Opaque document tokens: confidentiality, expiry, and fail-closed checks."""

import base64
import time

import pytest

from app.core.config import Settings
from app.providers.document_token import (
    InvalidDocumentToken,
    MissingTokenSecret,
    mint_document_token,
    mint_document_token_at_time,
    resolve_document_token,
)

PATH = "/manuals/Production/D0100.pdf"


def _settings(**overrides) -> Settings:
    overrides.setdefault("document_token_secret", "unit-test-secret-32-characters!!")
    return Settings(_env_file=None, **overrides)


def test_round_trip() -> None:
    settings = _settings()
    token = mint_document_token(settings, "alliance", PATH)
    assert resolve_document_token(settings, token, "alliance") == PATH


def test_token_contents_cannot_be_recovered_by_decoding() -> None:
    # The payload is ENCRYPTED, not merely encoded: base64-decoding the
    # token (or any slice of it) must not reveal the path or provider.
    token = mint_document_token(_settings(), "alliance", PATH)
    assert "manuals" not in token and "alliance" not in token
    padded = token + "=" * (-len(token) % 4)
    decoded = base64.urlsafe_b64decode(padded)
    for marker in (b"/manuals", b"alliance", b"D0100", b'{"p"'):
        assert marker not in decoded, f"{marker!r} readable in decoded token"


def test_expired_token_fails_closed() -> None:
    settings = _settings(document_token_ttl_seconds=900)
    now = int(time.time())
    token = mint_document_token_at_time(settings, "alliance", PATH, now - 901)
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(settings, token, "alliance", _now=now)
    # Same token within its lifetime still resolves.
    fresh = mint_document_token_at_time(settings, "alliance", PATH, now - 899)
    assert resolve_document_token(settings, fresh, "alliance", _now=now) == PATH


def test_future_issued_token_fails_closed() -> None:
    # Fernet allows 60s clock skew; beyond that a future timestamp is invalid.
    settings = _settings()
    now = int(time.time())
    token = mint_document_token_at_time(settings, "alliance", PATH, now + 120)
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(settings, token, "alliance", _now=now)


def test_tampered_token_fails_closed() -> None:
    settings = _settings()
    token = mint_document_token(settings, "alliance", PATH)
    middle = len(token) // 2
    flipped = token[:middle] + ("A" if token[middle] != "A" else "B") + token[middle + 1 :]
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(settings, flipped, "alliance")


@pytest.mark.parametrize("token", ["", "garbage", "gAAAAA", "%%%not-base64%%%", "a" * 200])
def test_malformed_tokens_fail_closed(token: str) -> None:
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(_settings(), token, "alliance")


def test_wrong_provider_fails_closed() -> None:
    settings = _settings()
    token = mint_document_token(settings, "alliance", PATH)
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(settings, token, "mock")


def test_wrong_secret_and_rotation_fail_closed() -> None:
    old = _settings(document_token_secret="old-secret-that-is-32-characters")
    new = _settings(document_token_secret="new-secret-that-is-32-characters")
    token = mint_document_token(old, "alliance", PATH)
    # Rotation: tokens minted under the old secret are all invalidated…
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(new, token, "alliance")
    # …and new mints under the new secret work.
    fresh = mint_document_token(new, "alliance", PATH)
    assert resolve_document_token(new, fresh, "alliance") == PATH


def test_production_missing_secret_refused() -> None:
    settings = Settings(_env_file=None, environment="production", document_token_secret="")
    with pytest.raises(MissingTokenSecret):
        mint_document_token(settings, "alliance", PATH)
    with pytest.raises(MissingTokenSecret):
        resolve_document_token(settings, "gAAAAAB", "alliance")


def test_production_short_secret_refused() -> None:
    settings = Settings(_env_file=None, environment="production", document_token_secret="too-short")
    with pytest.raises(MissingTokenSecret):
        mint_document_token(settings, "alliance", PATH)


def test_ephemeral_secret_allowed_outside_production() -> None:
    settings = Settings(_env_file=None, environment="test", document_token_secret="")
    token = mint_document_token(settings, "mock", "/mock/documents/x.pdf")
    assert resolve_document_token(settings, token, "mock") == "/mock/documents/x.pdf"


def test_mint_requires_provider_and_path() -> None:
    with pytest.raises(ValueError):
        mint_document_token(_settings(), "", PATH)
    with pytest.raises(ValueError):
        mint_document_token(_settings(), "alliance", "")
