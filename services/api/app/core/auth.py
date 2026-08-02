"""API key authentication (Milestone 11).

Until technician accounts exist, the API is protected by shared API keys
supplied per request. This is the minimum bar for exposing the service
publicly: the backend holds an authenticated provider session, so an
unauthenticated deployment would let anyone search and download documents
through it.

Design:
- Keys are provided in `API_KEYS` (comma-separated); each must be long and
  randomly generated. Compared in constant time; never logged.
- Header: `X-API-Key: <key>` (also accepted as `Authorization: Bearer <key>`
  so standard tooling works).
- Health/liveness/readiness endpoints stay open so load balancers and
  uptime checks work without a key.
- Production REFUSES TO START without keys — an unauthenticated public
  deployment must be impossible by accident. Development/test may run
  without keys (auth disabled) so local work and CI are unchanged.
"""

import hmac
import logging

from fastapi import Header, HTTPException, Request, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

MIN_KEY_LENGTH = 24

# Paths that never require a key: liveness/readiness probes and the
# OpenAPI docs (already disabled in production by the app factory).
_OPEN_PATH_SUFFIXES = ("/health", "/health/live", "/health/ready")


class InsecureConfiguration(RuntimeError):
    """Production configuration would expose the API without authentication."""


def validate_auth_configuration(settings: Settings) -> None:
    """Fail fast at startup rather than serving an open API in production."""
    if settings.environment != "production":
        return
    keys = settings.api_key_list
    if not keys:
        raise InsecureConfiguration(
            "API_KEYS must be set in production — refusing to start an unauthenticated API."
        )
    if any(len(key) < MIN_KEY_LENGTH for key in keys):
        raise InsecureConfiguration(
            f"every API key must be at least {MIN_KEY_LENGTH} characters and randomly generated."
        )


def _key_matches(candidate: str, configured: list[str]) -> bool:
    # compare_digest against every configured key (no early exit on match
    # position); the loop length depends only on how many keys are set.
    matched = False
    for key in configured:
        if hmac.compare_digest(candidate, key):
            matched = True
    return matched


def is_open_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _OPEN_PATH_SUFFIXES)


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Dependency enforcing API-key auth on protected routes.

    No-op when no keys are configured (development/test). Never logs the
    supplied value; failures carry no detail about why.
    """
    settings = get_settings()
    configured = settings.api_key_list
    if not configured:
        return  # auth disabled (non-production only; startup enforces this)
    if is_open_path(request.url.path):
        return

    supplied = x_api_key
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()

    if not supplied or not _key_matches(supplied, configured):
        logger.warning(
            "rejected unauthenticated request",
            extra={"path": request.url.path, "has_key": bool(supplied)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
