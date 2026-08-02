"""Opaque document tokens via authenticated encryption (Phase 3; ADR 0014).

The document API references provider documents without exposing provider
URLs/paths to clients and without persistence. Discovery mints a token
binding (provider id, provider-local source path); download authenticates,
decrypts and resolves it server-side.

Tokens are **Fernet** tokens (`cryptography` library): AES-128-CBC with an
HMAC-SHA256 authenticator and an embedded issued-at timestamp — a standard
maintained primitive, no custom cryptography. The payload is genuinely
confidential: a client cannot recover the provider path by decoding the
token. The encryption key is derived from the configured secret with
HKDF-SHA256.

Fail-closed properties (all raise `InvalidDocumentToken`, which callers map
to the same 404 as a missing document):
- malformed or truncated tokens;
- any tampering (authentication failure);
- expired tokens (older than the configured TTL, default 15 minutes);
- future-issued timestamps (beyond Fernet's 60 s clock-skew allowance);
- tokens minted for a different provider;
- tokens minted under a different (rotated) secret.

Secrets: production MUST configure `DOCUMENT_TOKEN_SECRET` (min 32 chars) —
document-token operations refuse (`MissingTokenSecret`) rather than silently
using a process-local secret. Development/tests may omit it, in which case
an ephemeral per-process secret is used (tokens then die with the process;
harmless — rediscovery re-mints). Rotating the secret invalidates every
outstanding token.
"""

import json
import secrets

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings

_MIN_PRODUCTION_SECRET_CHARS = 32
_HKDF_INFO = b"laundryconnect.document-token.v1"


class InvalidDocumentToken(Exception):
    """The token failed authentication, decryption, expiry, or provider
    binding. Message is structural only; callers respond identically to a
    missing document."""


class MissingTokenSecret(Exception):
    """Document-token operations are not configured for this environment
    (production without a valid `DOCUMENT_TOKEN_SECRET`). Mapped to 503."""


# Ephemeral per-process fallback secret — development and tests ONLY.
_ephemeral_secret: bytes | None = None


def _configured_secret(settings: Settings) -> bytes:
    secret = settings.document_token_secret
    if secret:
        if len(secret) < _MIN_PRODUCTION_SECRET_CHARS and settings.environment == "production":
            raise MissingTokenSecret(
                f"DOCUMENT_TOKEN_SECRET must be at least {_MIN_PRODUCTION_SECRET_CHARS} characters"
            )
        return secret.encode("utf-8")
    if settings.environment == "production":
        # Never silently degrade to an ephemeral secret in production.
        raise MissingTokenSecret("DOCUMENT_TOKEN_SECRET is required in production")
    global _ephemeral_secret
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_bytes(32)
    return _ephemeral_secret


def _fernet(settings: Settings) -> Fernet:
    key_material = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(_configured_secret(settings))
    import base64

    return Fernet(base64.urlsafe_b64encode(key_material))


def mint_document_token(settings: Settings, provider_id: str, source_path: str) -> str:
    """Encrypt (provider id, source path) into an opaque token. The payload
    is the minimum for the immediate request; issued-at is embedded by
    Fernet itself."""
    if not provider_id or not source_path:
        raise ValueError("provider_id and source_path are required")
    payload = json.dumps(
        {"p": provider_id, "s": source_path}, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return _fernet(settings).encrypt(payload).decode("ascii")


def resolve_document_token(
    settings: Settings,
    token: str,
    provider_id: str,
    *,
    _now: int | None = None,
) -> str:
    """Authenticate, decrypt, expiry-check and provider-check a token,
    returning its source path. Every failure mode raises
    `InvalidDocumentToken`. `_now` exists for deterministic expiry tests."""
    ttl = settings.document_token_ttl_seconds
    fernet = _fernet(settings)
    try:
        raw = token.encode("ascii")
        payload_bytes = (
            fernet.decrypt_at_time(raw, ttl=ttl, current_time=_now)
            if _now is not None
            else fernet.decrypt(raw, ttl=ttl)
        )
        payload = json.loads(payload_bytes)
    except InvalidToken:
        raise InvalidDocumentToken("token failed authentication or expired") from None
    except Exception:
        raise InvalidDocumentToken("token is malformed") from None
    if not isinstance(payload, dict):
        raise InvalidDocumentToken("token payload is invalid")
    source_path = payload.get("s")
    if payload.get("p") != provider_id or not isinstance(source_path, str) or not source_path:
        raise InvalidDocumentToken("token does not match this provider")
    return source_path


def mint_document_token_at_time(
    settings: Settings, provider_id: str, source_path: str, issued_at: int
) -> str:
    """Test helper: mint with an explicit issued-at so expiry and
    future-timestamp behaviour can be exercised deterministically. Not used
    by API routes."""
    if not provider_id or not source_path:
        raise ValueError("provider_id and source_path are required")
    payload = json.dumps(
        {"p": provider_id, "s": source_path}, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return _fernet(settings).encrypt_at_time(payload, issued_at).decode("ascii")
