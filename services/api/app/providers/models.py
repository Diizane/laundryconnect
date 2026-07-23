"""Normalised internal models shared by all provider connectors.

Connectors translate provider-specific responses into these models so that
core search never contains provider-specific behaviour. Every result carries
its `data_origin` so mock/manual/cached data can never masquerade as live.
"""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class QueryType(StrEnum):
    AUTO = "auto"
    MODEL = "model"
    SERIAL = "serial"
    PART = "part"
    FAULT_CODE = "fault_code"
    KEYWORD = "keyword"


class ResultType(StrEnum):
    DOCUMENT = "document"
    PART = "part"
    MODEL = "model"
    BULLETIN = "bulletin"
    DIAGRAM = "diagram"
    FAULT_CODE = "fault_code"


class DataOrigin(StrEnum):
    """Where a result's data actually comes from. Shown to technicians as a
    badge; mock/manual data must never be presented as live."""

    MOCK = "mock"
    MANUAL = "manual"  # manually indexed by staff
    LIVE = "live"
    CACHED = "cached"


class ProviderResult(BaseModel):
    """One normalised search result from a provider connector."""

    provider_id: str
    source_reference: str
    result_type: ResultType
    data_origin: DataOrigin
    title: str
    description: str | None = None

    manufacturer: str | None = None
    brand: str | None = None
    model: str | None = None
    serial_range: str | None = None

    document_type: str | None = None
    part_number: str | None = None
    revision: str | None = None
    published_at: date | None = None
    source_url: str | None = None
    access_method: Literal["direct", "provider_portal", "internal"] | None = None

    metadata: dict[str, str] = Field(default_factory=dict)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ProviderHealth(BaseModel):
    status: Literal["ok", "failed"]
    detail: str | None = None


class ProviderSearchStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DISABLED = "disabled"


class ProviderOutcome(BaseModel):
    """Per-provider outcome of one aggregated search.

    `error` carries only the exception class name — provider error messages
    could contain sensitive material and are logged server-side instead.
    """

    provider_id: str
    status: ProviderSearchStatus
    latency_ms: float | None = None
    result_count: int = 0
    error: str | None = None


class AggregatedSearch(BaseModel):
    """Results plus per-provider status for one fan-out search."""

    results: list[ProviderResult]
    providers: list[ProviderOutcome]
