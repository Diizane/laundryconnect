"""Response schemas for document endpoints.

Every document and search hit preserves full source traceability: provider,
official source reference, title, revision, origin (seeded_sample / live /
uploaded / cached), and page-text provenance — sample content is always
visibly labelled.
"""

import uuid
from datetime import date

from pydantic import BaseModel


class DocumentDetail(BaseModel):
    id: uuid.UUID
    title: str
    document_type: str
    provider: str
    source_reference: str
    source_url: str | None
    revision: str | None
    published_at: date | None
    language: str | None
    origin: str
    models: list[str]
    page_count: int


class DocumentPageContent(BaseModel):
    document_id: uuid.UUID
    page_number: int
    text_content: str
    text_source: str
    # True when extraction cut this page's text at the per-page cap; clients
    # (and future RAG citations) must not treat truncated text as complete.
    truncated: bool


class PageSearchHit(BaseModel):
    """One matching page: enough to cite (provider, document, revision,
    page) and to see exactly what kind of content it is."""

    document_id: uuid.UUID
    document_title: str
    provider: str
    source_reference: str
    revision: str | None
    origin: str
    page_number: int
    text_source: str
    snippet: str


class DocumentSearchResponse(BaseModel):
    document_id: uuid.UUID
    query: str
    total_hits: int
    limit: int
    hits: list[PageSearchHit]
