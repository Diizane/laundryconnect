"""Cache-aware document retrieval (Milestone 12).

Sits between the API and a provider connector. Order of preference:

1. **Cached copy, revalidated.** Ask the provider with the stored
   `ETag`/`Last-Modified`; a 304 means our copy is current and no body is
   transferred. Fast, and gentle on the provider.
2. **Fresh download.** No copy, or the provider says it was revised.
3. **Cached copy, unvalidated.** Only when the provider cannot answer at
   all — expired session, outage, provider error. This is what keeps
   technicians working when the session dies mid-job. The result is
   labelled `cached` with its age so the caller can be honest about it,
   and refused outright once it is older than the configured limit.

Caching is disabled by default; when disabled this is a straight
pass-through, so the pre-cache behaviour is exactly preserved.
"""

import logging
import time
from dataclasses import dataclass

from app.documents.cache import DocumentCache
from app.providers.alliance.transport import NotModified
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentContent,
    InvalidDocumentReference,
    ProviderDocumentsUnsupported,
    ProviderError,
)

logger = logging.getLogger(__name__)

# Provider answers that mean "this document is genuinely wrong/absent" —
# serving a stale copy would be misleading, so these are never masked.
_NEVER_MASK = (
    DocumentNotFound,
    InvalidDocumentReference,
    ProviderDocumentsUnsupported,
    InvalidDocumentContent,
)


@dataclass(frozen=True)
class FetchedDocument:
    body: bytes
    origin: str  # "live" | "cached"
    age_seconds: float = 0.0

    @property
    def is_cached(self) -> bool:
        return self.origin == "cached"


class CachingDocumentFetcher:
    def __init__(
        self,
        cache: DocumentCache | None,
        *,
        max_stale_seconds: int,
        now=time.time,
    ) -> None:
        self._cache = cache
        self._max_stale_seconds = max_stale_seconds
        self._now = now

    async def fetch(self, connector, provider_id: str, source_path: str) -> FetchedDocument:
        if self._cache is None:
            return FetchedDocument(await connector.fetch_document(source_path), origin="live")

        key = DocumentCache.key(provider_id, source_path)
        # A broken cache degrades to a plain fetch; it never fails a request.
        try:
            cached = self._cache.get(key)
        except OSError as exc:
            logger.warning(
                "document cache unreadable; fetching directly",
                extra={"provider": provider_id, "error": type(exc).__name__},
            )
            cached = None
        conditional = _conditional_headers(cached)

        try:
            body = await connector.fetch_document(source_path, conditional=conditional)
        except NotModified:
            # Provider confirms our copy is current: serve it, no transfer.
            if cached is None:
                # We sent no validators, so a 304 makes no sense — treat it
                # as a provider fault rather than serving nothing.
                raise
            self._cache.mark_revalidated(key)
            logger.info("document served from cache (revalidated)", extra={"provider": provider_id})
            return FetchedDocument(cached.body, origin="cached", age_seconds=0.0)
        except _NEVER_MASK:
            raise
        except ProviderError as exc:
            # Provider unreachable / session expired: fall back to our copy
            # if we have one that is not too old to trust.
            if cached is None:
                raise
            age = cached.age_seconds(self._now())
            if age > self._max_stale_seconds:
                logger.warning(
                    "cached document too old to serve",
                    extra={"provider": provider_id, "age_hours": round(age / 3600, 1)},
                )
                raise
            logger.warning(
                "serving cached document; provider unavailable",
                extra={
                    "provider": provider_id,
                    "error": type(exc).__name__,
                    "age_hours": round(age / 3600, 1),
                },
            )
            return FetchedDocument(cached.body, origin="cached", age_seconds=age)

        # Fresh copy (new, or the provider revised it). A cache write must
        # never break serving the document the technician asked for — an
        # unwritable cache directory is an operational problem, not a
        # reason to fail the request.
        validators = getattr(connector, "last_document_validators", {}) or {}
        try:
            self._cache.put(
                key,
                body,
                etag=validators.get("etag"),
                last_modified=validators.get("last_modified"),
            )
        except OSError as exc:
            logger.warning(
                "could not cache document; serving it anyway",
                extra={"provider": provider_id, "error": type(exc).__name__},
            )
        return FetchedDocument(body, origin="live")

    async def index(self, connector, provider_id: str, source_path: str):
        """Search/contents index for a document, built once and reused.

        The document itself is fetched through the normal cache-aware path,
        so this inherits revalidation, the expired-session fallback, and
        every provider gate.
        """
        from app.documents.pdf_index import DocumentIndex, build_index

        key = DocumentCache.key(provider_id, source_path) if self._cache else None
        if self._cache is not None:
            try:
                stored = self._cache.get_index(key)
            except OSError:
                stored = None
            if stored is not None:
                return DocumentIndex.from_json(stored)

        document = await self.fetch(connector, provider_id, source_path)
        try:
            index = build_index(document.body)
        except Exception as exc:
            # A provider serving an unparseable PDF must produce a clean
            # provider-content error, never an unhandled 500.
            logger.warning(
                "document could not be indexed",
                extra={"provider": provider_id, "error": type(exc).__name__},
            )
            raise InvalidDocumentContent("document could not be read") from None
        if self._cache is not None:
            try:
                self._cache.put_index(key, index.to_json())
            except OSError as exc:
                logger.warning(
                    "could not store document index; rebuilding next time",
                    extra={"provider": provider_id, "error": type(exc).__name__},
                )
        return index


def _conditional_headers(cached) -> dict[str, str] | None:
    if cached is None:
        return None
    headers: dict[str, str] = {}
    if cached.etag:
        headers["If-None-Match"] = cached.etag
    if cached.last_modified:
        headers["If-Modified-Since"] = cached.last_modified
    return headers or None
