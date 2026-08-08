"""Shared FastAPI dependencies for route modules."""

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.documents.cache import DocumentCache
from app.documents.fetcher import CachingDocumentFetcher
from app.providers.registry import ProviderRegistry
from app.search.service import SearchService

logger = logging.getLogger(__name__)


def get_provider_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session, or 503 if no database is configured.

    Commits on success, rolls back on any exception.
    """
    factory = request.app.state.db_session_factory
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]


def get_search_service(registry: RegistryDep, settings: SettingsDep) -> SearchService:
    return SearchService(registry, settings.provider_timeout_seconds)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


@lru_cache
def _document_cache_for(path: str, max_bytes: int) -> DocumentCache:
    """One cache instance per configured location (cheap; holds no state
    beyond the directory)."""
    return DocumentCache(Path(path), max_bytes=max_bytes)


def get_document_fetcher(settings: SettingsDep) -> CachingDocumentFetcher:
    """Cache-aware document retrieval. With caching disabled this is a
    straight pass-through to the provider, preserving prior behaviour."""
    cache = None
    if settings.document_cache_enabled:
        try:
            cache = _document_cache_for(
                settings.document_cache_path, settings.document_cache_max_bytes
            )
        except OSError:
            # An unusable cache directory must never break document serving.
            logger.warning("document cache unavailable; serving without it")
            cache = None
    return CachingDocumentFetcher(
        cache, max_stale_seconds=settings.document_cache_max_stale_seconds
    )


DocumentFetcherDep = Annotated[CachingDocumentFetcher, Depends(get_document_fetcher)]
