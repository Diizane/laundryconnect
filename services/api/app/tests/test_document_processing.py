"""PDF extraction safeguards and snippet-building tests."""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from app.documents.extraction import (
    ExtractionError,
    ExtractionFailure,
    ExtractionLimits,
    extract_page_texts,
)
from app.documents.snippets import build_snippet

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "sample_manual.pdf"


class TestExtraction:
    def test_extracts_text_per_page_in_order(self) -> None:
        pages = list(extract_page_texts(FIXTURE_PDF))
        assert len(pages) == 2
        assert "Fault code EdL" in pages[0]
        assert "Maintenance schedule" in pages[1]

    def test_invalid_file_raises_unreadable(self, tmp_path: Path) -> None:
        not_a_pdf = tmp_path / "not_a_pdf.pdf"
        not_a_pdf.write_bytes(b"this is not a pdf")
        with pytest.raises(ExtractionError) as excinfo:
            list(extract_page_texts(not_a_pdf))
        assert excinfo.value.reason == ExtractionFailure.UNREADABLE

    def test_encrypted_pdf_rejected(self, tmp_path: Path) -> None:
        writer = PdfWriter()
        for page in PdfReader(FIXTURE_PDF).pages:
            writer.add_page(page)
        writer.encrypt("password")
        encrypted = tmp_path / "encrypted.pdf"
        with encrypted.open("wb") as handle:
            writer.write(handle)

        with pytest.raises(ExtractionError) as excinfo:
            list(extract_page_texts(encrypted))
        assert excinfo.value.reason == ExtractionFailure.ENCRYPTED

    def test_oversized_file_rejected(self) -> None:
        limits = ExtractionLimits(max_file_bytes=10)
        with pytest.raises(ExtractionError) as excinfo:
            list(extract_page_texts(FIXTURE_PDF, limits))
        assert excinfo.value.reason == ExtractionFailure.FILE_TOO_LARGE

    def test_too_many_pages_rejected(self) -> None:
        limits = ExtractionLimits(max_pages=1)
        with pytest.raises(ExtractionError) as excinfo:
            list(extract_page_texts(FIXTURE_PDF, limits))
        assert excinfo.value.reason == ExtractionFailure.TOO_MANY_PAGES

    def test_timeout_enforced(self) -> None:
        limits = ExtractionLimits(max_seconds=0.0)
        with pytest.raises(ExtractionError) as excinfo:
            list(extract_page_texts(FIXTURE_PDF, limits))
        assert excinfo.value.reason == ExtractionFailure.TIMEOUT

    def test_page_text_truncated_at_cap(self) -> None:
        limits = ExtractionLimits(max_text_chars_per_page=10)
        pages = list(extract_page_texts(FIXTURE_PDF, limits))
        assert all(len(page) <= 10 for page in pages)

    def test_errors_carry_reason_and_detail(self, tmp_path: Path) -> None:
        not_a_pdf = tmp_path / "bad.pdf"
        not_a_pdf.write_bytes(b"nope")
        with pytest.raises(ExtractionError) as excinfo:
            list(extract_page_texts(not_a_pdf))
        assert excinfo.value.detail
        assert str(excinfo.value).startswith("unreadable:")


class TestSnippets:
    def test_snippet_windows_around_match(self) -> None:
        text = ("filler " * 50) + "the EdL door lock error appears here" + (" filler" * 50)
        snippet = build_snippet(text, "edl")
        assert snippet is not None
        assert "EdL door lock error" in snippet
        assert snippet.startswith("…")
        assert snippet.endswith("…")
        assert len(snippet) < 250

    def test_snippet_at_start_has_no_leading_ellipsis(self) -> None:
        snippet = build_snippet("EdL means door lock error. More text follows.", "EdL")
        assert snippet is not None
        assert snippet.startswith("EdL")

    def test_snippet_collapses_whitespace(self) -> None:
        snippet = build_snippet("door\n\nlock\t error EdL", "EdL")
        assert snippet is not None
        assert "door lock error EdL" in snippet

    def test_repeated_matches_use_first_occurrence(self) -> None:
        text = "first EdL here" + (" filler" * 60) + " second EdL there"
        snippet = build_snippet(text, "EdL")
        assert snippet is not None
        assert "first EdL" in snippet
        assert "second EdL" not in snippet

    def test_query_whitespace_normalised_like_text(self) -> None:
        snippet = build_snippet("check the door lock assembly", "door  lock")
        assert snippet is not None
        assert "door lock assembly" in snippet

    def test_no_match_returns_none_not_fallback(self) -> None:
        assert build_snippet("Some page text without the term.", "zzz") is None

    def test_blank_query_returns_none(self) -> None:
        assert build_snippet("Some page text.", "   ") is None

    def test_unusual_characters_returned_verbatim(self) -> None:
        text = 'Voltage <400V> & "phase" 100% — see §4 F_8'
        snippet = build_snippet(text, "100%")
        assert snippet is not None
        assert "100%" in snippet
        assert "<400V>" in snippet  # no escaping/mangling; JSON handles transport
