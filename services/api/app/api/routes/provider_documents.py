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
import time

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from app.api.deps import (
    DocumentFetcherDep,
    DrawingIndexStoreDep,
    RegistryDep,
    SettingsDep,
)
from app.documents.drawing_index import DrawingIndex, IndexedDrawing, IndexedPart
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
from app.schemas.provider_documents import (
    ContentsEntryOut,
    DocumentContentsResponse,
    DocumentDiscoveryResponse,
    DocumentSearchHitOut,
    DocumentSearchResultsResponse,
    DrawingCalloutOut,
    DrawingListResponse,
    DrawingPartOut,
    DrawingResponse,
    DrawingSearchMatchOut,
    DrawingSearchResponse,
    DrawingSummaryOut,
    ProviderDocumentOut,
)

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
    fetcher: DocumentFetcherDep,
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
        document = await fetcher.fetch(connector, provider_id, source_path)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    return Response(
        content=document.body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{_sanitise_filename(source_path)}"',
            # The client never stores documents; any caching happens
            # server-side under revalidation (ADR 0015).
            "Cache-Control": "no-store",
            # Honest labelling, consistent with data_origin on search
            # results: whether this copy came from the provider just now or
            # from the server cache, and how stale it may be.
            "X-Document-Origin": document.origin,
            "X-Document-Age-Seconds": str(int(document.age_seconds)),
        },
    )


def _resolve_or_404(settings, token: str, provider_id: str) -> str:
    """Shared token resolution for the read-only document endpoints."""
    try:
        return resolve_document_token(settings, token, provider_id)
    except MissingTokenSecret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document tokens are not configured for this environment.",
        ) from None
    except InvalidDocumentToken:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.") from None


@router.get("/{token}/contents", response_model=DocumentContentsResponse)
async def document_contents(
    registry: RegistryDep,
    settings: SettingsDep,
    fetcher: DocumentFetcherDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    token: str = Path(pattern=_TOKEN_PATTERN),
) -> DocumentContentsResponse:
    """Page count, whether the document can be searched, and its embedded
    contents with page numbers so a client can jump to a heading."""
    connector = _connector_or_404(registry, provider_id)
    source_path = _resolve_or_404(settings, token, provider_id)
    try:
        index = await fetcher.index(connector, provider_id, source_path)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    return DocumentContentsResponse(
        page_count=index.page_count,
        searchable=index.is_searchable,
        searchable_pages=index.searchable_pages,
        contents=[
            ContentsEntryOut(title=e.title, page_number=e.page_number, depth=e.depth)
            for e in index.contents
        ],
    )


@router.get("/{token}/search", response_model=DocumentSearchResultsResponse)
async def search_within_document(
    registry: RegistryDep,
    settings: SettingsDep,
    fetcher: DocumentFetcherDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    token: str = Path(pattern=_TOKEN_PATTERN),
    q: str = Query(min_length=1, max_length=100, description="Text to find in the document"),
) -> DocumentSearchResultsResponse:
    """Find text inside one document, returning page-cited snippets.

    Reports `searchable=false` for documents with no usable text layer so
    an empty result is never mistaken for "no matches".
    """
    from app.documents.pdf_index import search_index

    connector = _connector_or_404(registry, provider_id)
    source_path = _resolve_or_404(settings, token, provider_id)
    try:
        index = await fetcher.index(connector, provider_id, source_path)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    hits = search_index(index, q) if index.is_searchable else []
    return DocumentSearchResultsResponse(
        query=q,
        searchable=index.is_searchable,
        total_hits=len(hits),
        hits=[DocumentSearchHitOut(page_number=h.page_number, snippet=h.snippet) for h in hits],
    )


drawings_router = APIRouter(prefix="/providers/{provider_id}/drawings", tags=["provider-drawings"])


@drawings_router.get("", response_model=DrawingListResponse)
async def list_drawings(
    registry: RegistryDep,
    settings: SettingsDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    ref: str = Query(pattern=_REF_PATTERN, description="The search result's document reference"),
) -> DrawingListResponse:
    """Assembly drawings available for one machine.

    Each carries an opaque token; provider paths never reach the client.
    """
    connector = _connector_or_404(registry, provider_id)
    if not hasattr(connector, "discover_drawings"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This provider does not support drawings.",
        )
    try:
        drawings = await connector.discover_drawings(ref)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    try:
        return DrawingListResponse(
            provider_id=provider_id,
            drawings=[
                DrawingSummaryOut(
                    token=mint_document_token(settings, provider_id, d.source_path),
                    title=d.title,
                    drawing_id=d.drawing_id,
                )
                for d in drawings
            ],
        )
    except MissingTokenSecret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document tokens are not configured for this environment.",
        ) from None


@drawings_router.get("/search", response_model=DrawingSearchResponse)
async def search_drawings(
    registry: RegistryDep,
    settings: SettingsDep,
    index_store: DrawingIndexStoreDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    ref: str = Query(pattern=_REF_PATTERN, description="The search result's document reference"),
    q: str = Query(min_length=1, max_length=64, description="What to look for"),
) -> DrawingSearchResponse:
    """Which of a machine's drawings to open for a given part.

    Searching titles alone cannot answer "where is the drive belt?" — no
    title contains the word. This searches every drawing's parts list,
    using an index built once per machine from the provider's combined
    print page (one request rather than one per drawing).

    The index decides only which drawing to suggest. Opening one always
    fetches it live, so an old index cannot show stale contents.
    """
    connector = _connector_or_404(registry, provider_id)
    if not hasattr(connector, "fetch_drawing_sections"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This provider does not support drawings.",
        )

    index = index_store.get(provider_id, ref)
    if index is None:
        try:
            sections = await connector.fetch_drawing_sections(ref)
        except ProviderError as exc:
            _raise_for_provider_error(exc, provider_id)
        index = DrawingIndex(
            built_at=time.time(),
            drawings=tuple(
                IndexedDrawing(
                    title=section.title,
                    parts=tuple(
                        IndexedPart(
                            reference=part.reference,
                            part_number=part.part_number,
                            description=part.description,
                        )
                        for part in section.parts
                    ),
                )
                for section in sections
            ),
        )
        index_store.put(provider_id, ref, index)
        logger.info(
            "drawing index built",
            extra={"provider": provider_id, "drawings": len(index.drawings)},
        )

    # A suggestion is only useful if it can be opened, so it has to be
    # matched back to a listed drawing to get a token.
    try:
        listed = {d.title: d for d in await connector.discover_drawings(ref)}
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)

    results: list[DrawingSearchMatchOut] = []
    try:
        for drawing, matched in index.search(q):
            link = listed.get(drawing.title)
            if link is None:
                continue  # indexed but not listed: nothing to open
            results.append(
                DrawingSearchMatchOut(
                    token=mint_document_token(settings, provider_id, link.source_path),
                    title=drawing.title,
                    drawing_id=link.drawing_id,
                    matches=[
                        DrawingPartOut(
                            reference=part.reference,
                            part_number=part.part_number,
                            description=part.description,
                        )
                        for part in matched
                    ],
                )
            )
    except MissingTokenSecret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document tokens are not configured for this environment.",
        ) from None

    return DrawingSearchResponse(
        provider_id=provider_id,
        query=q,
        index_age_seconds=round(index.age_seconds(time.time()), 1),
        results=results,
    )


@drawings_router.get("/{token}", response_model=DrawingResponse)
async def get_drawing(
    registry: RegistryDep,
    settings: SettingsDep,
    provider_id: str = Path(pattern=r"^[a-z0-9_-]{1,32}$"),
    token: str = Path(pattern=_TOKEN_PATTERN),
) -> DrawingResponse:
    """One drawing's vector diagram and parts list."""
    connector = _connector_or_404(registry, provider_id)
    if not hasattr(connector, "fetch_drawing"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="This provider does not support drawings."
        )
    source_path = _resolve_or_404(settings, token, provider_id)
    try:
        drawing = await connector.fetch_drawing(source_path)
    except ProviderError as exc:
        _raise_for_provider_error(exc, provider_id)
    return DrawingResponse(
        svg=drawing.svg,
        view_box=list(drawing.view_box) if drawing.view_box else None,
        callouts=[
            DrawingCalloutOut(reference=c.reference, x=c.x, y=c.y, radius=c.radius)
            for c in drawing.callouts
        ],
        parts=[
            DrawingPartOut(
                reference=p.reference,
                part_number=p.part_number,
                description=p.description,
                comments=p.comments,
            )
            for p in drawing.parts
        ],
    )
