"""PDF extraction and snippet-building tests."""

from pathlib import Path

import pytest

from app.documents.extraction import ExtractionError, extract_page_texts
from app.documents.snippets import build_snippet

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "sample_manual.pdf"


class TestExtraction:
    def test_extracts_text_per_page_in_order(self) -> None:
        pages = list(extract_page_texts(FIXTURE_PDF))
        assert len(pages) == 2
        assert "Fault code EdL" in pages[0]
        assert "Maintenance schedule" in pages[1]

    def test_invalid_file_raises_extraction_error(self, tmp_path: Path) -> None:
        not_a_pdf = tmp_path / "not_a_pdf.pdf"
        not_a_pdf.write_bytes(b"this is not a pdf")
        with pytest.raises(ExtractionError):
            list(extract_page_texts(not_a_pdf))


class TestSnippets:
    def test_snippet_windows_around_match(self) -> None:
        text = ("filler " * 50) + "the EdL door lock error appears here" + (" filler" * 50)
        snippet = build_snippet(text, "edl")
        assert "EdL door lock error" in snippet
        assert snippet.startswith("…")
        assert snippet.endswith("…")
        assert len(snippet) < 250

    def test_snippet_at_start_has_no_leading_ellipsis(self) -> None:
        snippet = build_snippet("EdL means door lock error. More text follows.", "EdL")
        assert snippet.startswith("EdL")

    def test_snippet_collapses_whitespace(self) -> None:
        snippet = build_snippet("door\n\nlock\t error EdL", "EdL")
        assert "door lock error EdL" in snippet

    def test_no_match_falls_back_to_text_start(self) -> None:
        snippet = build_snippet("Some page text without the term.", "zzz")
        assert snippet.startswith("Some page text")
