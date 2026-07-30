"""Signed opaque document tokens (Milestone 9 Phase 3; ADR 0014).

The document API must reference provider documents without exposing provider
URLs/paths to clients and without persistence. Discovery therefore mints a
signed, versioned, opaque token binding (provider id, provider-local source
path); download resolves it server-side. Standard HMAC-SHA256 (stdlib), no
custom cryptography. Tampering, truncation, version or provider mismatch all
fail closed with `InvalidDocumentToken` — callers map that to a response
that leaks nothing (404).

Tokens are stateless and carry no session data or expiry: their lifetime is
bounded by the signing secret (rotate `DOCUMENT_TOKEN_SECRET` to invalidate
all outstanding tokens). Possession of a token grants nothing by itself —
every download still passes the provider's live gates, host allowlist, and
content validation at fetch time.
"""

import base64
import hashlib
import hmac
import json
import secrets

from app.core.config import Settings

_VERSION = "v1"
_SIGNATURE_BYTES = 32  # full HMAC-SHA256


class InvalidDocumentToken(Exception):
    """The token failed validation (malformed, tampered, wrong version, or
    bound to a different provider). Message is structural only."""


# Ephemeral per-process fallback secret for development and tests. Production
# must set DOCUMENT_TOKEN_SECRET (tokens then survive restarts/workers).
_ephemeral_secret: bytes | None = None


def token_secret(settings: Settings) -> bytes:
    if settings.document_token_secret:
        return settings.document_token_secret.encode("utf-8")
    global _ephemeral_secret
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_bytes(32)
    return _ephemeral_secret


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _signature(secret: bytes, signed_part: str) -> bytes:
    return hmac.new(secret, signed_part.encode("utf-8"), hashlib.sha256).digest()


def mint_document_token(secret: bytes, provider_id: str, source_path: str) -> str:
    """Create a token binding (provider_id, source_path). The payload is the
    minimum needed for the immediate request — nothing else is embedded."""
    if not provider_id or not source_path:
        raise ValueError("provider_id and source_path are required")
    payload = json.dumps(
        {"p": provider_id, "s": source_path}, separators=(",", ":"), sort_keys=True
    )
    body = _b64encode(payload.encode("utf-8"))
    signature = _b64encode(_signature(secret, f"{_VERSION}.{body}"))
    return f"{_VERSION}.{body}.{signature}"


def resolve_document_token(secret: bytes, token: str, provider_id: str) -> str:
    """Verify a token and return its source path. Every failure mode —
    malformed, bad signature, wrong version, provider mismatch, unexpected
    payload — raises `InvalidDocumentToken` (fail closed, constant-time
    signature comparison)."""
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _VERSION:
        raise InvalidDocumentToken("token structure is invalid")
    version, body, signature = parts
    try:
        provided = _b64decode(signature)
        expected = _signature(secret, f"{version}.{body}")
        if len(provided) != _SIGNATURE_BYTES or not hmac.compare_digest(provided, expected):
            raise InvalidDocumentToken("token signature is invalid")
        payload = json.loads(_b64decode(body))
    except InvalidDocumentToken:
        raise
    except Exception:
        raise InvalidDocumentToken("token is malformed") from None
    if not isinstance(payload, dict):
        raise InvalidDocumentToken("token payload is invalid")
    source_path = payload.get("s")
    if payload.get("p") != provider_id or not isinstance(source_path, str) or not source_path:
        raise InvalidDocumentToken("token does not match this provider")
    return source_path
