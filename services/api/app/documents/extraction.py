"""Page-level text extraction from PDF files, with resource safeguards.

pypdf reads pages lazily from the file, so large manuals are processed page
by page rather than loaded into memory whole. All failure modes surface as a
typed `ExtractionError` with a machine-readable reason — raw library
exceptions never escape this module.
"""

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Defaults sized for large commercial-equipment manuals; callers may tighten
# them (tests do) but the constants are the production ceiling (ADR 0009).
MAX_FILE_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_PAGES = 3000
MAX_TEXT_CHARS_PER_PAGE = 50_000
MAX_EXTRACTION_SECONDS = 300.0


class ExtractionFailure(StrEnum):
    UNREADABLE = "unreadable"
    ENCRYPTED = "encrypted"
    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    TIMEOUT = "timeout"


@dataclass
class ExtractionLimits:
    max_file_bytes: int = MAX_FILE_BYTES
    max_pages: int = MAX_PAGES
    max_text_chars_per_page: int = MAX_TEXT_CHARS_PER_PAGE
    max_seconds: float = MAX_EXTRACTION_SECONDS


class ExtractionError(Exception):
    """The file could not be safely extracted."""

    def __init__(self, reason: ExtractionFailure, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail


def extract_page_texts(pdf_path: Path, limits: ExtractionLimits | None = None) -> Iterator[str]:
    """Yield the text of each page in order (empty string for blank pages).

    Raises `ExtractionError` for unreadable, encrypted, oversized, or
    over-long extractions. One unreadable page yields empty text rather than
    failing the whole manual; page text is truncated at the per-page cap.
    """
    limits = limits or ExtractionLimits()

    file_size = pdf_path.stat().st_size
    if file_size > limits.max_file_bytes:
        raise ExtractionError(
            ExtractionFailure.FILE_TOO_LARGE,
            f"{file_size} bytes exceeds limit of {limits.max_file_bytes}",
        )

    try:
        reader = PdfReader(pdf_path)
        encrypted = reader.is_encrypted
    except Exception as exc:
        raise ExtractionError(
            ExtractionFailure.UNREADABLE, f"cannot open PDF ({type(exc).__name__})"
        ) from exc

    if encrypted:
        raise ExtractionError(ExtractionFailure.ENCRYPTED, "encrypted PDFs are not supported")

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise ExtractionError(
            ExtractionFailure.UNREADABLE, f"cannot read page tree ({type(exc).__name__})"
        ) from exc
    if page_count > limits.max_pages:
        raise ExtractionError(
            ExtractionFailure.TOO_MANY_PAGES,
            f"{page_count} pages exceeds limit of {limits.max_pages}",
        )

    started = time.monotonic()
    for index, page in enumerate(reader.pages, start=1):
        if time.monotonic() - started > limits.max_seconds:
            raise ExtractionError(
                ExtractionFailure.TIMEOUT,
                f"extraction exceeded {limits.max_seconds}s at page {index}",
            )
        try:
            text = page.extract_text() or ""
        except Exception:
            # One unreadable page must not sink the whole manual.
            logger.warning(
                "page text extraction failed",
                extra={"page_number": index, "file": pdf_path.name},
            )
            text = ""
        yield text[: limits.max_text_chars_per_page]
