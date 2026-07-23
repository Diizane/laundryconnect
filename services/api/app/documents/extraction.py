"""Page-level text extraction from PDF files.

pypdf reads pages lazily from the file, so large manuals are processed
page by page rather than loaded into memory whole.
"""

import logging
from collections.abc import Iterator
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """The file could not be read as a PDF."""


def extract_page_texts(pdf_path: Path) -> Iterator[str]:
    """Yield the text of each page, in order (empty string for blank pages)."""
    try:
        reader = PdfReader(pdf_path)
    except Exception as exc:
        raise ExtractionError(f"Cannot read PDF: {type(exc).__name__}") from exc

    for index, page in enumerate(reader.pages, start=1):
        try:
            yield page.extract_text() or ""
        except Exception:
            # One unreadable page must not sink the whole manual.
            logger.warning(
                "page text extraction failed",
                extra={"page_number": index, "file": pdf_path.name},
            )
            yield ""
