"""Isolated extraction worker: hard timeout, typed error round-trips."""

import time
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extraction import ExtractionError, ExtractionFailure
from app.documents.ingestion import ingest_pdf_pages
from app.documents.worker import extract_pages_isolated
from app.models import PageTextSource
from app.repositories.documents import DocumentRepository
from app.repositories.providers import ProviderRepository

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "sample_manual.pdf"


async def test_worker_extracts_fixture_pages() -> None:
    pages = await extract_pages_isolated(FIXTURE_PDF)
    assert len(pages) == 2
    assert "Fault code EdL" in pages[0].text
    assert "Maintenance schedule" in pages[1].text
    assert all(not page.truncated for page in pages)


async def test_worker_round_trips_typed_errors(tmp_path: Path) -> None:
    writer = PdfWriter()
    for page in PdfReader(FIXTURE_PDF).pages:
        writer.add_page(page)
    writer.encrypt("password")
    encrypted = tmp_path / "encrypted.pdf"
    with encrypted.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(ExtractionError) as excinfo:
        await extract_pages_isolated(encrypted)
    assert excinfo.value.reason == ExtractionFailure.ENCRYPTED


async def test_worker_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as excinfo:
        await extract_pages_isolated(tmp_path / "missing.pdf")
    assert excinfo.value.reason == ExtractionFailure.FILE_NOT_FOUND


async def test_hung_worker_is_killed_at_hard_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wall-clock limit must kill a hung child — not wait it out."""
    monkeypatch.setenv("LC_EXTRACTION_TEST_HANG_SECONDS", "30")
    started = time.monotonic()
    with pytest.raises(ExtractionError) as excinfo:
        await extract_pages_isolated(FIXTURE_PDF, hard_timeout_seconds=1.5)
    elapsed = time.monotonic() - started

    assert excinfo.value.reason == ExtractionFailure.TIMEOUT
    assert "killed" in excinfo.value.detail
    assert elapsed < 10, f"hard kill took {elapsed:.1f}s — timeout is not enforced"


async def test_isolated_ingestion_replaces_pages(db_session: AsyncSession) -> None:
    provider = await ProviderRepository(db_session).create(slug="mock", name="Mock")
    repo = DocumentRepository(db_session)
    document = await repo.create(
        title="Manual",
        document_type="service_manual",
        provider_id=provider.id,
        source_reference="ref-worker",
        origin="seeded_sample",
    )

    count = await ingest_pdf_pages(db_session, document, FIXTURE_PDF, isolated=True)
    await db_session.commit()

    assert count == 2
    page = await repo.get_page(document.id, 1)
    assert page is not None
    assert "Fault code EdL" in page.text_content
    assert page.text_source == PageTextSource.NATIVE_PDF.value
