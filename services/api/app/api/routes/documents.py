"""Document endpoints: metadata, page content, and in-document search.

Pages are served and searched individually — large manuals are never
returned whole. Search responses are bounded (default/max limits) and
deterministic (page-number order); execution timing goes to the logs.
"""

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import DbSessionDep
from app.documents.snippets import build_snippet
from app.models import Document, MachineModel, ModelDocument
from app.repositories.documents import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    DocumentRepository,
)
from app.schemas.documents import (
    DocumentDetail,
    DocumentPageContent,
    DocumentSearchResponse,
    PageSearchHit,
)

logger = logging.getLogger(__name__)

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
    model_numbers = list(
        await session.scalars(
            select(MachineModel.model_number)
            .join(ModelDocument, ModelDocument.machine_model_id == MachineModel.id)
            .where(ModelDocument.document_id == document_id)
            .order_by(MachineModel.model_number)
        )
    )
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
        origin=document.origin,
        models=model_numbers,
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
        document_id=document_id,
        page_number=page.page_number,
        text_content=page.text_content,
        text_source=page.text_source,
        truncated=page.truncated,
    )


@router.get("/{document_id}/search", response_model=DocumentSearchResponse)
async def search_document(
    session: DbSessionDep,
    document_id: uuid.UUID,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
) -> DocumentSearchResponse:
    """Search inside one document; every hit cites its page number.

    Results are ordered by page number and capped at `limit`
    (max {MAX_SEARCH_LIMIT}); `total_hits` reports all matching pages so
    truncation is visible. Offset-based pagination is planned (ADR 0009).
    """
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search query must be at least 2 characters.",
        )
    document = await _get_document_or_404(session, document_id)

    started = time.perf_counter()
    pages, total = await DocumentRepository(session).search_pages(document_id, query, limit)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "document search executed",
        extra={
            "document_id": str(document_id),
            "result_count": len(pages),
            "total_matches": total,
            "limit": limit,
            "duration_ms": duration_ms,
        },
    )

    hits = []
    for page in pages:
        snippet = build_snippet(page.text_content, query)
        if snippet is None:
            # The database matched but the snippet builder did not — a
            # semantics mismatch worth surfacing, never papered over with
            # unrelated context.
            logger.warning(
                "snippet builder missed a database match",
                extra={"document_id": str(document_id), "page_number": page.page_number},
            )
            snippet = f"(match on page {page.page_number})"
        hits.append(
            PageSearchHit(
                document_id=document.id,
                document_title=document.title,
                provider=document.provider.slug,
                source_reference=document.source_reference,
                revision=document.revision,
                origin=document.origin,
                page_number=page.page_number,
                text_source=page.text_source,
                snippet=snippet,
            )
        )
    return DocumentSearchResponse(
        document_id=document.id, query=query, total_hits=total, limit=limit, hits=hits
    )
