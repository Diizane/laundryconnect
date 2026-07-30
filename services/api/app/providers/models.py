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
    FIXTURE = "fixture"  # replayed recorded/synthetic fixtures — NOT live
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


class ProviderDocumentInfo(BaseModel):
    """One document discovered through a provider's bounded document
    workflow (Milestone 9). Carried through provider models only — never
    persisted, never cached. `source_path` is the provider-internal path to
    the document bytes; it is resolved and fetched by the backend and must
    never be handed to a mobile client (the backend proxies the bytes)."""

    provider_id: str
    data_origin: DataOrigin
    title: str
    document_type: str | None = None
    part_number: str | None = None
    comment: str | None = None
    languages: list[str] = Field(default_factory=list)
    # Provider-side categorisation and filename, e.g. from
    # /manuals/<category>/<filename>.pdf (query strings never included).
    category: str | None = None
    filename: str | None = None
    source_path: str
    # False when the provider lists the document without a downloadable file.
    available: bool = True


class ProviderHealth(BaseModel):
    status: Literal["ok", "failed"]
    detail: str | None = None


class ProviderSearchStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DISABLED = "disabled"
    # A live provider session is missing, invalid, or expired; a human must
    # re-authenticate via the manual bootstrap. Never an automatic bypass.
    REAUTH_REQUIRED = "reauthentication_required"
    # The provider refused access (e.g. 403) — a hard stop for human review.
    FORBIDDEN = "forbidden"


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
