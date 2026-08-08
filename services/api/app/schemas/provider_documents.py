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


class DrawingSummaryOut(BaseModel):
    """One assembly drawing offered for a machine."""

    token: str
    title: str
    drawing_id: str | None = None


class DrawingListResponse(BaseModel):
    provider_id: str
    drawings: list[DrawingSummaryOut] = Field(default_factory=list)


class DrawingSearchMatchOut(BaseModel):
    """One drawing a search suggests, and why."""

    token: str
    title: str
    drawing_id: str | None = None
    # The parts whose description, number or callout matched. Empty when
    # only the drawing's own name matched.
    matches: list["DrawingPartOut"] = Field(default_factory=list)


class DrawingSearchResponse(BaseModel):
    """Where to look for something across a machine's drawings.

    `index_age_seconds` is how old the parts index behind this answer is.
    The index only decides which drawing to suggest; opening one always
    fetches it live, so an old index can never show stale contents.
    """

    provider_id: str
    query: str
    index_age_seconds: float
    results: list[DrawingSearchMatchOut] = Field(default_factory=list)


class DrawingPartOut(BaseModel):
    reference: str
    part_number: str
    description: str
    comments: str | None = None


class DrawingCalloutOut(BaseModel):
    """A numbered marker on the diagram, in the diagram's own coordinates.

    `reference` matches a `DrawingPartOut.reference`. A part marked in two
    places yields two callouts, and both are tappable.
    """

    reference: str
    x: float
    y: float
    radius: float


class DrawingResponse(BaseModel):
    """A drawing's diagram, its parts list, and the markers joining them.

    `svg` is the vector diagram, safe to render directly. `view_box` is the
    coordinate space the callouts are expressed in — `[min_x, min_y, width,
    height]` — and is null when the diagram declares none, in which case
    `callouts` is empty because a tap could not be mapped to it.

    Only callouts whose number and position are both certain, and which
    match a row in `parts`, are listed; see
    docs/MILESTONE_15/drawings-discovery.md.
    """

    svg: str
    view_box: list[float] | None = None
    callouts: list[DrawingCalloutOut] = Field(default_factory=list)
    parts: list[DrawingPartOut] = Field(default_factory=list)
