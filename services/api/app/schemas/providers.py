"""Response schemas for provider endpoints.

These schemas deliberately expose only operational metadata — never
credentials, sessions, or raw provider responses.
"""

from typing import Literal

from pydantic import BaseModel

from app.providers.models import DataOrigin


class ProviderStatusItem(BaseModel):
    provider_id: str
    display_name: str
    data_origin: DataOrigin
    enabled: bool
    status: Literal["ok", "failed", "timed_out", "disabled"]
    latency_ms: float | None = None
    detail: str | None = None


class ProvidersStatusResponse(BaseModel):
    providers: list[ProviderStatusItem]
