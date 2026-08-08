"""Provider-document API schemas (Milestone 9 Phase 3; ADR 0014).

Client-safe by construction: these schemas carry NO provider URLs, paths,
hostnames, or internal identifiers. A document is referenced only by its
signed opaque `token` (absent when the provider lists it without a
downloadable file).
"""

from pydantic import BaseModel, Field

from app.providers.models import DataOrigin


class ProviderDocumentOut(BaseModel):
    """One document a provider offers — metadata plus an opaque token."""

    token: str | None = Field(
        default=None,
        description=(
            "Opaque signed reference for the download endpoint. Null when the "
            "document is listed but not downloadable."
        ),
    )
    title: str
    document_type: str | None = None
    part_number: str | None = None
    comment: str | None = None
    languages: list[str] = Field(default_factory=list)
    category: str | None = None
    filename: str | None = None
    available: bool
    data_origin: DataOrigin


class DocumentDiscoveryResponse(BaseModel):
    provider_id: str
    documents: list[ProviderDocumentOut]


class ContentsEntryOut(BaseModel):
    """One heading from the document's embedded contents."""

    title: str
    page_number: int
    depth: int = 0


class DocumentContentsResponse(BaseModel):
    page_count: int
    # False when the PDF carries no usable text layer (a scan, or fonts
    # without character maps) — the client should say so rather than
    # offering a search that can only ever return nothing.
    searchable: bool
    searchable_pages: int
    contents: list[ContentsEntryOut] = Field(default_factory=list)


class DocumentSearchHitOut(BaseModel):
    page_number: int
    snippet: str


class DocumentSearchResultsResponse(BaseModel):
    query: str
    searchable: bool
    total_hits: int
    hits: list[DocumentSearchHitOut] = Field(default_factory=list)
