"""Provider document discovery + download proxy (Milestone 9 Phase 3).

The mobile client never sees or constructs a provider URL: discovery accepts
a provider-validated reference (for Alliance, the numeric catalog identifiers
already present in search-result metadata) and returns metadata with signed
opaque tokens; download resolves a token server-side and proxies the
validated PDF bytes. Provider authentication stays entirely on the backend.

Error mapping is deliberate and leak-free (ADR 0014): domain errors map to
stable statuses; invalid/tampered tokens are indistinguishable from missing
documents (404); raw exception text and upstream URLs are never returned.
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from app.api.deps import RegistryDep, SettingsDep
from app.providers.base import ProviderConnector
from app.providers.document_token import (
    InvalidDocumentToken,
    MissingTokenSecret,
    mint_document_token,
    resolve_document_token,
)
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentContent,
    InvalidDocumentReference,
    LiveModeRefused,
    ProviderDocumentsUnsupported,
    ProviderError,
    ProviderForbidden,
    ReauthenticationRequired,
)
from app.schemas.provider_documents import DocumentDiscoveryResponse, ProviderDocumentOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers/{provider_id}/documents", tags=["provider-documents"])

# Generic surface constraints; the provider applies its own strict semantic
# validation on top (e.g. Alliance requires '<digits>:<digits>').
_REF_PATTERN = r"^[A-Za-z0-9:._-]{1,64}$"
# Fernet tokens: urlsafe base64 with '=' padding, no dots.
_TOKEN_PATTERN = r"^[A-Za-z0-9_=-]{1,1024}$"  # noqa: S105 - URL-safe charset regex, not a secret
_FILENAME_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,120}\.pdf$")


def _connector_or_404(registry: RegistryDep, provider_id: str) -> ProviderConnector:
    """Unknown and disabled providers are indistinguishable (404)."""
    try:
        entry = registry.get(provider_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider not found.") from None
    if not entry.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider not found.")
    return entry.connector


def _raise_for_provider_error(exc: ProviderError, provider_id: str) -> None:
    """Map domain errors to stable, leak-free HTTP responses. Logs carry the
    exception class name only — messages may reference provider internals."""
    logger.warning(
        "provider document operation failed",
        extra={"provider": provider_id, "error": type(exc).__name__},
    )
    if isinstance(exc, DocumentNotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.") from None
    if isinstance(exc, InvalidDocumentReference):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Invalid document reference."
        ) from None
    if isinstance(exc, ProviderDocumentsUnsupported):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This provider does not support document retrieval.",
        ) from None
    if isinstance(exc, ReauthenticationRequired):
        # Existing provider status contract: an operator must re-run the
        # manual session bootstrap; the client retries later.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provider session requires reauthentication.",
        ) from None
    if isinstance(exc, ProviderForbidden):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Provider refused access."
        ) from None
    if isinstance(exc, InvalidDocumentContent):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Provider returned invalid document content.",
        ) from None
    if isinstance(exc, LiveModeRefused):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provider live access is not enabled in this environment.",
        ) from None
    # Transient/transport failure (timeouts, 5xx, size caps): provider-local
    # failure, never provider detail.
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Provider request failed.") from None


def _sanitise_filename(source_path: str) -> str:
    """A response filename derived from the provider filename, or a safe
    constant — never a client-influenced or path-bearing value."""
    candidate = source_path.rsplit("/", 1)[-1]
    if _FILENAME_SAFE.match(candidate):
        return candidate
    return "document.pdf"


@router.get("", response_model=DocumentDiscoveryResponse)
async def discover_documents(
    registry: RegistryDep,
    settings: SettingsDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    ref: str = Query(
        pattern=_REF_PATTERN,
        description=(
            "The search result's document reference (provider-validated; for "
            "Alliance this is '<manual id>:<model id>' from result metadata)."
        ),
    ),
) -> DocumentDiscoveryResponse:
    """List the documents a provider offers for one search result.

    Returns client-safe metadata only: no provider URLs, paths, or internal
    identifiers. Downloadable documents carry an opaque signed `token` for
    the download endpoint.
    """
    connector = _connector_or_404(registry, provider_id)
    try:
        documents = await connector.discover_documents(ref)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    try:
        tokens = {
            info.source_path: mint_document_token(settings, provider_id, info.source_path)
            for info in documents
            if info.available and info.source_path
        }
    except MissingTokenSecret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document tokens are not configured for this environment.",
        ) from None
    return DocumentDiscoveryResponse(
        provider_id=provider_id,
        documents=[
            ProviderDocumentOut(
                token=tokens.get(info.source_path),
                title=info.title,
                document_type=info.document_type,
                part_number=info.part_number,
                comment=info.comment,
                languages=info.languages,
                category=info.category,
                filename=info.filename,
                available=info.available,
                data_origin=info.data_origin,
            )
            for info in documents
        ],
    )


@router.get(
    "/{token}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_document(
    registry: RegistryDep,
    settings: SettingsDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    token: str = Path(pattern=_TOKEN_PATTERN),
) -> Response:
    """Proxy one validated PDF from the provider to the client.

    The token is resolved and verified server-side; a tampered, malformed,
    or wrong-provider token is indistinguishable from a missing document.
    Bytes are validated by the provider (Content-Type + %PDF magic) before
    they reach this route; nothing is persisted or cached.
    """
    connector = _connector_or_404(registry, provider_id)
    try:
        source_path = resolve_document_token(settings, token, provider_id)
    except MissingTokenSecret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document tokens are not configured for this environment.",
        ) from None
    except InvalidDocumentToken:
        # Deliberately identical to a missing document — leaks nothing.
        # Covers malformed, tampered, EXPIRED, future-issued, and
        # wrong-provider tokens alike.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.") from None
    try:
        body = await connector.fetch_document(source_path)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{_sanitise_filename(source_path)}"',
            # Milestone 9 has no caching anywhere; make that explicit to
            # intermediaries and the client.
            "Cache-Control": "no-store",
        },
    )
