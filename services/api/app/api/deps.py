"""Shared FastAPI dependencies for route modules."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.providers.registry import ProviderRegistry
from app.search.service import SearchService


def get_provider_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]


def get_search_service(registry: RegistryDep, settings: SettingsDep) -> SearchService:
    return SearchService(registry, settings.provider_timeout_seconds)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
