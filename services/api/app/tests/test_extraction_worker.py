"""Isolated extraction worker: lifecycle cleanup, protocol strictness, limits."""

import asyncio
import json
import subprocess
import time
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.extraction import (
    ExtractionError,
    ExtractionFailure,
    ExtractionLimits,
    extract_page_texts,
)
from app.documents.ingestion import ingest_pdf_pages
from app.documents.worker import _parse_worker_output, extract_pages_isolated
from app.models import PageTextSource
from app.repositories.documents import DocumentRepository
from app.repositories.providers import ProviderRepository

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "sample_manual.pdf"


def _worker_pids() -> list[int]:
    result = subprocess.run(["pgrep", "-f", "app.documents.worker"], capture_output=True, text=True)
    return [int(pid) for pid in result.stdout.split()]


def _process_state(pid: int) -> str | None:
    """Return the ps state string for pid, or None once fully reaped/gone."""
    result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    state = result.stdout.strip()
    return state or None


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


async def test_hung_worker_is_killed_at_hard_deadline() -> None:
    """The wall-clock limit must kill a hung child — not wait it out."""
    started = time.monotonic()
    with pytest.raises(ExtractionError) as excinfo:
        await extract_pages_isolated(FIXTURE_PDF, hard_timeout_seconds=1.5, _test_hang_seconds=30)
    elapsed = time.monotonic() - started

    assert excinfo.value.reason == ExtractionFailure.TIMEOUT
    assert "killed" in excinfo.value.detail
    assert elapsed < 10, f"hard kill took {elapsed:.1f}s — timeout is not enforced"


async def test_cancellation_kills_and_reaps_worker() -> None:
    """Cancelling the parent must terminate the child: no orphan, no zombie."""
    assert _worker_pids() == [], "stray extraction workers before test"

    task = asyncio.create_task(extract_pages_isolated(FIXTURE_PDF, _test_hang_seconds=30))
    # Wait until the child process is actually running.
    for _ in range(100):
        if _worker_pids():
            break
        await asyncio.sleep(0.1)
    [pid] = _worker_pids()

    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    cancel_elapsed = time.monotonic() - started
    assert cancel_elapsed < 5, f"cancellation took {cancel_elapsed:.1f}s"

    # The child must die and be reaped (no zombie) shortly after.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = _process_state(pid)
        if state is None:
            break
        assert not state.startswith("Z"), f"worker {pid} left as zombie ({state})"
        await asyncio.sleep(0.1)
    assert _process_state(pid) is None, "worker still alive after cancellation"
    assert _worker_pids() == []


async def test_env_hang_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stray service environment variable must not stall extractions."""
    monkeypatch.setenv("LC_EXTRACTION_TEST_HANG_SECONDS", "30")
    started = time.monotonic()
    pages = await extract_pages_isolated(FIXTURE_PDF)
    assert len(pages) == 2
    assert time.monotonic() - started < 8, "worker honoured an env hang variable"


async def test_worker_enforces_total_text_cap() -> None:
    limits = ExtractionLimits(max_total_text_chars=30)
    with pytest.raises(ExtractionError) as excinfo:
        await extract_pages_isolated(FIXTURE_PDF, limits)
    assert excinfo.value.reason == ExtractionFailure.TOTAL_TEXT_TOO_LARGE


def test_in_process_extraction_enforces_total_text_cap() -> None:
    limits = ExtractionLimits(max_total_text_chars=30)
    with pytest.raises(ExtractionError) as excinfo:
        list(extract_page_texts(FIXTURE_PDF, limits))
    assert excinfo.value.reason == ExtractionFailure.TOTAL_TEXT_TOO_LARGE


class TestWorkerProtocolValidation:
    """Every malformed worker output shape must become a typed UNREADABLE."""

    @pytest.mark.parametrize(
        "payload",
        [
            b"not json at all",
            b"\xff\xfe garbage bytes",
            json.dumps([]).encode(),  # JSON list instead of object
            json.dumps({"pages": []}).encode(),  # missing ok
            json.dumps({"ok": "true", "pages": []}).encode(),  # ok as string
            json.dumps({"ok": 1, "pages": []}).encode(),  # ok as int
            json.dumps({"ok": True, "pages": None}).encode(),  # null pages
            json.dumps({"ok": True, "pages": "SC60"}).encode(),  # pages as string
            json.dumps({"ok": True, "pages": [123]}).encode(),  # page not object
            json.dumps({"ok": True, "pages": [{"text": 123, "truncated": False}]}).encode(),
            json.dumps({"ok": True, "pages": [{"text": "x"}]}).encode(),  # missing truncated
            json.dumps(
                {"ok": True, "pages": [{"text": "x", "truncated": "yes"}]}
            ).encode(),  # truncated non-bool
            json.dumps({"ok": False, "reason": "made_up_reason", "detail": "d"}).encode(),
            json.dumps({"ok": False, "reason": None, "detail": "d"}).encode(),
            json.dumps({"ok": False, "reason": "encrypted", "detail": 42}).encode(),
        ],
    )
    def test_malformed_output_becomes_unreadable(self, payload: bytes) -> None:
        with pytest.raises(ExtractionError) as excinfo:
            _parse_worker_output(payload)
        assert excinfo.value.reason == ExtractionFailure.UNREADABLE
        assert "invalid worker output" in excinfo.value.detail

    def test_valid_success_payload_parses(self) -> None:
        payload = json.dumps(
            {"ok": True, "pages": [{"text": "hello", "truncated": True}], "extra": 1}
        ).encode()
        [page] = _parse_worker_output(payload)
        assert page.text == "hello"
        assert page.truncated is True  # unexpected extra fields ignored

    def test_valid_failure_payload_reraises_typed_reason(self) -> None:
        payload = json.dumps({"ok": False, "reason": "encrypted", "detail": "locked"}).encode()
        with pytest.raises(ExtractionError) as excinfo:
            _parse_worker_output(payload)
        assert excinfo.value.reason == ExtractionFailure.ENCRYPTED
        assert excinfo.value.detail == "locked"


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
