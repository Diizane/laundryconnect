"""Page-level text extraction from PDF files, with resource safeguards.

pypdf reads pages lazily from the file stream, so this module yields pages
one at a time — but note that the ingestion path (`ingest_pdf_pages`)
materialises ALL extracted page text in memory before replacing database
rows, by design (extract fully before touching existing pages, ADR 0009).
The limits below bound that materialisation; see ADR 0010 for the sizing
rationale and the staging-table plan for manuals beyond them.

All failure modes surface as a typed `ExtractionError` with a
machine-readable reason — raw library or OS exceptions never escape.
"""

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Sized for commercial-laundry manuals (service/parts/installation manuals
# observed well under 500 pages). Worst-case in-memory materialisation is
# max_pages * max_text_chars_per_page = 30M characters (~60 MB) — see
# ADR 0010; larger manuals need the documented staging-table strategy.
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_PAGES = 1500
MAX_TEXT_CHARS_PER_PAGE = 20_000
# COOPERATIVE limit: checked between pages only. It cannot interrupt a hung
# page.extract_text() call. Before accepting arbitrary uploads or live
# provider documents, extraction must run in an isolated worker process
# with a hard wall-clock timeout and resource limits (ADR 0010).
MAX_EXTRACTION_SECONDS = 300.0


class ExtractionFailure(StrEnum):
    UNREADABLE = "unreadable"
    ENCRYPTED = "encrypted"
    FILE_NOT_FOUND = "file_not_found"
    NOT_A_FILE = "not_a_file"
    FILE_ACCESS = "file_access"
    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    TIMEOUT = "timeout"


@dataclass
class ExtractionLimits:
    max_file_bytes: int = MAX_FILE_BYTES
    max_pages: int = MAX_PAGES
    max_text_chars_per_page: int = MAX_TEXT_CHARS_PER_PAGE
    max_seconds: float = MAX_EXTRACTION_SECONDS


@dataclass(frozen=True)
class ExtractedPage:
    """One page of extracted text; `truncated` records whether the per-page
    character cap cut the text (observable, never silent — ADR 0010)."""

    text: str
    truncated: bool = False


class ExtractionError(Exception):
    """The file could not be safely extracted."""

    def __init__(self, reason: ExtractionFailure, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail


def _checked_file_size(pdf_path: Path) -> int:
    """Validate the path is a readable regular file and return its size."""
    try:
        if not pdf_path.exists():
            raise ExtractionError(ExtractionFailure.FILE_NOT_FOUND, str(pdf_path.name))
        if not pdf_path.is_file():
            raise ExtractionError(
                ExtractionFailure.NOT_A_FILE, f"{pdf_path.name} is not a regular file"
            )
        return pdf_path.stat().st_size
    except OSError as exc:
        raise ExtractionError(
            ExtractionFailure.FILE_ACCESS, f"cannot access file ({type(exc).__name__})"
        ) from exc


def extract_page_texts(
    pdf_path: Path, limits: ExtractionLimits | None = None
) -> Iterator[ExtractedPage]:
    """Yield each page's extracted text in order.

    Raises `ExtractionError` (typed reason, no raw OS/library exceptions)
    for missing/unreadable/non-regular files, encrypted or malformed PDFs,
    oversized files, too many pages, or exceeding the cooperative time
    budget. One unreadable page yields empty text rather than failing the
    whole manual; text beyond the per-page cap is truncated with
    `truncated=True` and a logged warning.
    """
    limits = limits or ExtractionLimits()

    file_size = _checked_file_size(pdf_path)
    if file_size > limits.max_file_bytes:
        raise ExtractionError(
            ExtractionFailure.FILE_TOO_LARGE,
            f"{file_size} bytes exceeds limit of {limits.max_file_bytes}",
        )

    try:
        stream = pdf_path.open("rb")
    except OSError as exc:
        raise ExtractionError(
            ExtractionFailure.FILE_ACCESS, f"cannot open file ({type(exc).__name__})"
        ) from exc

    with stream:
        try:
            reader = PdfReader(stream)
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
                ExtractionFailure.UNREADABLE,
                f"cannot read page tree ({type(exc).__name__})",
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

            truncated = len(text) > limits.max_text_chars_per_page
            if truncated:
                logger.warning(
                    "page text truncated at per-page cap",
                    extra={
                        "page_number": index,
                        "file": pdf_path.name,
                        "original_chars": len(text),
                        "cap": limits.max_text_chars_per_page,
                    },
                )
                text = text[: limits.max_text_chars_per_page]
            yield ExtractedPage(text=text, truncated=truncated)
