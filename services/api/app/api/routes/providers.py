"""Provider status endpoints."""

import asyncio
import time

from fastapi import APIRouter

from app.api.deps import RegistryDep, SettingsDep
from app.providers.registry import RegisteredProvider
from app.schemas.providers import ProvidersStatusResponse, ProviderStatusItem

router = APIRouter(prefix="/providers", tags=["providers"])


async def _check_one(entry: RegisteredProvider, timeout_seconds: float) -> ProviderStatusItem:
    connector = entry.connector
    base = {
        "provider_id": connector.provider_id,
        "display_name": connector.display_name,
        "data_origin": connector.data_origin,
        "enabled": entry.enabled,
    }
    if not entry.enabled:
        return ProviderStatusItem(**base, status="disabled")

    started = time.perf_counter()
    try:
        health = await asyncio.wait_for(connector.health_check(), timeout_seconds)
    except TimeoutError:
        return ProviderStatusItem(**base, status="timed_out")
    except Exception:
        # Detail stays server-side; provider errors may contain sensitive
        # material and must not leak through the API.
        return ProviderStatusItem(**base, status="failed")

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return ProviderStatusItem(
        **base, status=health.status, latency_ms=latency_ms, detail=health.detail
    )


@router.get("/status", response_model=ProvidersStatusResponse)
async def providers_status(registry: RegistryDep, settings: SettingsDep) -> ProvidersStatusResponse:
    items = await asyncio.gather(
        *(_check_one(entry, settings.provider_timeout_seconds) for entry in registry.all())
    )
    return ProvidersStatusResponse(providers=list(items))
