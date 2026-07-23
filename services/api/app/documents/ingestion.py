"""Document page ingestion: extract fully, then replace atomically.

Ordering guarantee (ADR 0009): extraction runs to completion BEFORE any
existing page is touched. If extraction raises, the document's current pages
are never modified. Replacement itself happens inside the caller's
transaction (the repository only flushes), so an insertion failure rolls
back to the previous page set — a partial page set can never be committed.

Memory model (ADR 0010): although extraction yields pages lazily, this
function MATERIALISES all extracted page text in memory (the price of the
extract-before-delete safety guarantee). The extraction limits bound that
materialisation to roughly max_pages * max_text_chars_per_page characters;
manuals beyond the limits need the staging-table strategy documented in
ADR 0010, not a limit increase.
"""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extraction import ExtractionLimits, extract_page_texts
from app.models import Document, PageTextSource
from app.repositories.documents import DocumentRepository, PageInput

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
    pages = [
        PageInput(text=extracted.text, truncated=extracted.truncated)
        for extracted in extract_page_texts(pdf_path, limits)
    ]

    count = await DocumentRepository(session).replace_pages(
        document, pages, text_source=PageTextSource.NATIVE_PDF.value
    )
    truncated_pages = sum(1 for page in pages if page.truncated)
    logger.info(
        "document pages ingested",
        extra={
            "document_id": str(document.id),
            "page_count": count,
            "truncated_pages": truncated_pages,
        },
    )
    return count
