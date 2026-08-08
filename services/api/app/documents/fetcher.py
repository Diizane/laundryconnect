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
        cached = self._cache.get(key)
        conditional = _conditional_headers(cached)

        try:
            body = await connector.fetch_document(source_path, conditional=conditional)
        except NotModified:
            # Provider confirms our copy is current: serve it, no transfer.
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

        # Fresh copy (new, or the provider revised it).
        validators = getattr(connector, "last_document_validators", {}) or {}
        self._cache.put(
            key,
            body,
            etag=validators.get("etag"),
            last_modified=validators.get("last_modified"),
        )
        return FetchedDocument(body, origin="live")


def _conditional_headers(cached) -> dict[str, str] | None:
    if cached is None:
        return None
    headers: dict[str, str] = {}
    if cached.etag:
        headers["If-None-Match"] = cached.etag
    if cached.last_modified:
        headers["If-Modified-Since"] = cached.last_modified
    return headers or None
