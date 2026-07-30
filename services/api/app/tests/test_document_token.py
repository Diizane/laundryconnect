"""Opaque document token: mint/resolve round-trip and fail-closed behaviour."""

import pytest

from app.core.config import Settings
from app.providers.document_token import (
    InvalidDocumentToken,
    mint_document_token,
    resolve_document_token,
    token_secret,
)

SECRET = b"test-secret-32-bytes-aaaaaaaaaaaa"


def test_round_trip() -> None:
    token = mint_document_token(SECRET, "alliance", "/manuals/Production/D0100.pdf")
    assert resolve_document_token(SECRET, token, "alliance") == "/manuals/Production/D0100.pdf"


def test_token_is_opaque() -> None:
    # The raw path must not be readable without decoding — no plain substring.
    token = mint_document_token(SECRET, "alliance", "/manuals/Production/D0100.pdf")
    assert "/manuals" not in token
    assert "alliance" not in token


def test_tampered_body_fails_closed() -> None:
    token = mint_document_token(SECRET, "alliance", "/manuals/Production/D0100.pdf")
    version, body, signature = token.split(".")
    flipped = ("A" if body[0] != "A" else "B") + body[1:]
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(SECRET, f"{version}.{flipped}.{signature}", "alliance")


def test_tampered_signature_fails_closed() -> None:
    token = mint_document_token(SECRET, "alliance", "/manuals/Production/D0100.pdf")
    version, body, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(SECRET, f"{version}.{body}.{flipped}", "alliance")


@pytest.mark.parametrize(
    "token",
    ["", "garbage", "v1.only-two", "v2.a.b", "v1..", "v1.%%%.%%%", "a.b.c.d"],
)
def test_malformed_tokens_fail_closed(token: str) -> None:
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(SECRET, token, "alliance")


def test_wrong_provider_fails_closed() -> None:
    token = mint_document_token(SECRET, "alliance", "/manuals/Production/D0100.pdf")
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(SECRET, token, "mock")


def test_wrong_secret_fails_closed() -> None:
    token = mint_document_token(SECRET, "alliance", "/manuals/Production/D0100.pdf")
    with pytest.raises(InvalidDocumentToken):
        resolve_document_token(b"other-secret", token, "alliance")


def test_configured_secret_used_and_stable() -> None:
    settings = Settings(_env_file=None, document_token_secret="configured-secret")
    assert token_secret(settings) == b"configured-secret"


def test_ephemeral_secret_is_stable_within_process() -> None:
    settings = Settings(_env_file=None, document_token_secret="")
    assert token_secret(settings) == token_secret(settings)
    token = mint_document_token(token_secret(settings), "mock", "/mock/documents/x.pdf")
    assert resolve_document_token(token_secret(settings), token, "mock") == (
        "/mock/documents/x.pdf"
    )


def test_mint_requires_provider_and_path() -> None:
    with pytest.raises(ValueError):
        mint_document_token(SECRET, "", "/manuals/x/y.pdf")
    with pytest.raises(ValueError):
        mint_document_token(SECRET, "alliance", "")
