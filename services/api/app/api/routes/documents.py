"""Document endpoints: metadata, page content, and in-document search.

Pages are served and searched individually — large manuals are never
returned whole.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import DbSessionDep
from app.documents.snippets import build_snippet
from app.models import Document
from app.repositories.documents import DocumentRepository
from app.schemas.documents import (
    DocumentDetail,
    DocumentPageContent,
    DocumentSearchResponse,
    PageSearchHit,
)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _get_document_or_404(session: DbSessionDep, document_id: uuid.UUID) -> Document:
    document = await session.scalar(
        select(Document).options(joinedload(Document.provider)).where(Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(session: DbSessionDep, document_id: uuid.UUID) -> DocumentDetail:
    document = await _get_document_or_404(session, document_id)
    page_count = await DocumentRepository(session).page_count(document_id)
    return DocumentDetail(
        id=document.id,
        title=document.title,
        document_type=document.document_type,
        provider=document.provider.slug,
        source_reference=document.source_reference,
        source_url=document.source_url,
        revision=document.revision,
        published_at=document.published_at,
        language=document.language,
        page_count=page_count,
    )


@router.get("/{document_id}/pages/{page_number}", response_model=DocumentPageContent)
async def get_document_page(
    session: DbSessionDep, document_id: uuid.UUID, page_number: int
) -> DocumentPageContent:
    await _get_document_or_404(session, document_id)
    page = await DocumentRepository(session).get_page(document_id, page_number)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found.")
    return DocumentPageContent(
        document_id=document_id, page_number=page.page_number, text_content=page.text_content
    )


@router.get("/{document_id}/search", response_model=DocumentSearchResponse)
async def search_document(
    session: DbSessionDep,
    document_id: uuid.UUID,
    q: str = Query(min_length=2, max_length=200),
) -> DocumentSearchResponse:
    """Search inside one document; every hit cites its page number."""
    document = await _get_document_or_404(session, document_id)
    pages = await DocumentRepository(session).search_pages(document_id, q)
    hits = [
        PageSearchHit(
            document_id=document.id,
            document_title=document.title,
            provider=document.provider.slug,
            page_number=page.page_number,
            snippet=build_snippet(page.text_content, q),
        )
        for page in pages
    ]
    return DocumentSearchResponse(document_id=document.id, query=q, total_hits=len(hits), hits=hits)
