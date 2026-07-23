"""Response schemas for document endpoints."""

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
    page_count: int


class DocumentPageContent(BaseModel):
    document_id: uuid.UUID
    page_number: int
    text_content: str


class PageSearchHit(BaseModel):
    """One matching page: enough to cite (document, page) and jump there."""

    document_id: uuid.UUID
    document_title: str
    provider: str
    page_number: int
    snippet: str


class DocumentSearchResponse(BaseModel):
    document_id: uuid.UUID
    query: str
    total_hits: int
    hits: list[PageSearchHit]
