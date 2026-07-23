"""Transactional safety of document page replacement (ADR 0009).

Existing pages must survive extraction failures and insertion failures;
only a fully successful replacement may change the indexed page set.
"""

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extraction import ExtractionError
from app.documents.ingestion import ingest_pdf_pages
from app.models import PageTextSource
from app.repositories.documents import DocumentRepository
from app.repositories.providers import ProviderRepository

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "sample_manual.pdf"

ORIGINAL_PAGES = ["original page one", "original page two", "original page three"]


async def _document_with_pages(session: AsyncSession):
    provider = await ProviderRepository(session).create(slug="mock", name="Mock")
    repo = DocumentRepository(session)
    document = await repo.create(
        title="Manual",
        document_type="service_manual",
        provider_id=provider.id,
        source_reference="ref-1",
        origin="seeded_sample",
    )
    await repo.replace_pages(
        document, ORIGINAL_PAGES, text_source=PageTextSource.SEEDED_SAMPLE.value
    )
    await session.commit()
    return document


async def _page_texts(session: AsyncSession, document_id) -> list[str]:
    repo = DocumentRepository(session)
    count = await repo.page_count(document_id)
    pages = [await repo.get_page(document_id, n) for n in range(1, count + 1)]
    return [page.text_content for page in pages if page is not None]


async def test_extraction_failure_leaves_existing_pages_intact(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    document = await _document_with_pages(db_session)
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"this is not a pdf at all")

    with pytest.raises(ExtractionError):
        await ingest_pdf_pages(db_session, document, corrupt)

    assert await _page_texts(db_session, document.id) == ORIGINAL_PAGES


async def test_insertion_failure_rolls_back_to_existing_pages(
    db_session: AsyncSession,
) -> None:
    document = await _document_with_pages(db_session)
    document_id = document.id
    repo = DocumentRepository(db_session)

    # A None text violates NOT NULL mid-replacement: the delete and the
    # partial inserts must all roll back together.
    bad_pages = ["new page one", None, "new page three"]
    with pytest.raises(IntegrityError):
        await repo.replace_pages(document, bad_pages, text_source="native_pdf")  # type: ignore[arg-type]
    await db_session.rollback()

    assert await _page_texts(db_session, document_id) == ORIGINAL_PAGES


async def test_successful_replacement_removes_obsolete_pages(
    db_session: AsyncSession,
) -> None:
    document = await _document_with_pages(db_session)
    repo = DocumentRepository(db_session)

    count = await repo.replace_pages(
        document, ["fresh one", "fresh two"], text_source=PageTextSource.NATIVE_PDF.value
    )
    await db_session.commit()

    assert count == 2
    assert await repo.page_count(document.id) == 2
    assert await _page_texts(db_session, document.id) == ["fresh one", "fresh two"]
    # No orphaned page 3 remains.
    assert await repo.get_page(document.id, 3) is None


async def test_successful_ingestion_replaces_pages_with_provenance(
    db_session: AsyncSession,
) -> None:
    document = await _document_with_pages(db_session)

    count = await ingest_pdf_pages(db_session, document, FIXTURE_PDF)
    await db_session.commit()

    assert count == 2
    repo = DocumentRepository(db_session)
    page = await repo.get_page(document.id, 1)
    assert page is not None
    assert "Fault code EdL" in page.text_content
    assert page.text_source == PageTextSource.NATIVE_PDF.value


async def test_pages_carry_seeded_sample_provenance(db_session: AsyncSession) -> None:
    document = await _document_with_pages(db_session)
    page = await DocumentRepository(db_session).get_page(document.id, 1)
    assert page is not None
    assert page.text_source == PageTextSource.SEEDED_SAMPLE.value
