"""Document page ingestion: extract fully, then replace atomically.

Ordering guarantee (ADR 0009): extraction runs to completion BEFORE any
existing page is touched. If extraction raises, the document's current pages
are never modified. Replacement itself happens inside the caller's
transaction (the repository only flushes), so an insertion failure rolls
back to the previous page set — a partial page set can never be committed.
"""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extraction import ExtractionLimits, extract_page_texts
from app.models import Document, PageTextSource
from app.repositories.documents import DocumentRepository

logger = logging.getLogger(__name__)


async def ingest_pdf_pages(
    session: AsyncSession,
    document: Document,
    pdf_path: Path,
    limits: ExtractionLimits | None = None,
) -> int:
    """Extract a PDF and replace the document's indexed pages.

    Raises `ExtractionError` (document pages untouched) on any extraction
    failure. Returns the number of pages indexed. The caller owns the
    transaction and must commit.
    """
    # Fully materialise before touching existing pages — see module docstring.
    page_texts = list(extract_page_texts(pdf_path, limits))

    count = await DocumentRepository(session).replace_pages(
        document, page_texts, text_source=PageTextSource.NATIVE_PDF.value
    )
    logger.info(
        "document pages ingested",
        extra={"document_id": str(document.id), "page_count": count},
    )
    return count
