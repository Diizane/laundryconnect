"""Shared FastAPI dependencies for route modules."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.providers.registry import ProviderRegistry
from app.search.service import SearchService


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
