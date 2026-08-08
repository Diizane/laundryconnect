"""In-document search and contents (Milestone 13) — offline."""

import pytest

from app.documents.pdf_index import (
    ContentsEntry,
    DocumentIndex,
    search_index,
    text_quality,
)


class TestTextQuality:
    """Detects PDFs whose fonts carry no character map, so extraction yields
    glyph codes instead of words. A real Alliance manual (D0167) is entirely
    like this — searching it would silently return nothing."""

    def test_real_words_score_high(self) -> None:
        assert text_quality("Remove the drive belt and inspect the pulley") == 1.0

    def test_glyph_codes_score_zero(self) -> None:
        assert text_quality("/G68/G82/G50/G48 /G68/G82/G51/G48") == 0.0

    def test_empty_text_scores_zero(self) -> None:
        assert text_quality("   \n  ") == 0.0

    def test_mixed_content_scores_between(self) -> None:
        score = text_quality("Belt tension /G68/G82 adjustment /G50/G48")
        assert 0.0 < score < 1.0


class TestSearchableFlag:
    def test_document_with_text_is_searchable(self) -> None:
        index = DocumentIndex(page_count=2, page_texts=["drive belt", "motor pulley"])
        assert index.is_searchable is True
        assert index.searchable_pages == 2

    def test_glyph_only_document_is_not_searchable(self) -> None:
        index = DocumentIndex(page_count=2, page_texts=["/G68/G82", "/G50/G48"])
        assert index.is_searchable is False
        assert index.searchable_pages == 0

    def test_partially_readable_document_is_searchable(self) -> None:
        index = DocumentIndex(page_count=2, page_texts=["/G68/G82", "drive belt tension"])
        assert index.is_searchable is True
        assert index.searchable_pages == 1


class TestSearch:
    def _index(self) -> DocumentIndex:
        return DocumentIndex(
            page_count=3,
            page_texts=[
                "Cover page for the drying tumbler manual",
                "Remove the drive belt before servicing the motor",
                "Thermostat replacement requires draining the unit",
            ],
        )

    def test_finds_a_term_and_cites_its_page(self) -> None:
        hits = search_index(self._index(), "drive belt")
        assert len(hits) == 1
        assert hits[0].page_number == 2
        assert "drive belt" in hits[0].snippet.lower()

    def test_search_is_case_insensitive(self) -> None:
        assert search_index(self._index(), "THERMOSTAT")[0].page_number == 3

    def test_absent_term_returns_nothing(self) -> None:
        assert search_index(self._index(), "hydraulic ram") == []

    def test_blank_query_returns_nothing(self) -> None:
        assert search_index(self._index(), "   ") == []

    def test_unreadable_pages_are_skipped_not_matched(self) -> None:
        # A glyph-encoded page must never produce a hit, even for a term
        # that appears in its raw extraction.
        index = DocumentIndex(page_count=1, page_texts=["/G68/G82 belt /G50/G48 /G51 /G52 /G53"])
        assert search_index(index, "belt") == []

    def test_results_are_capped(self) -> None:
        index = DocumentIndex(page_count=200, page_texts=["the drive belt"] * 200)
        assert len(search_index(index, "belt", limit=10)) == 10


class TestIndexSerialisation:
    def test_round_trip_preserves_contents_and_text(self) -> None:
        original = DocumentIndex(
            page_count=2,
            page_texts=["cover", "drive belt"],
            contents=[
                ContentsEntry(title="Cover", page_number=1),
                ContentsEntry(title="Drive", page_number=2, depth=1),
            ],
        )
        restored = DocumentIndex.from_json(original.to_json())
        assert restored.page_count == 2
        assert restored.page_texts == ["cover", "drive belt"]
        assert [(c.title, c.page_number, c.depth) for c in restored.contents] == [
            ("Cover", 1, 0),
            ("Drive", 2, 1),
        ]
        # Search still works after a round trip through the cache.
        assert search_index(restored, "belt")[0].page_number == 2


class TestBuildIndexFromRealPdf:
    """Against the minimal PDF fixture — build_index must never raise for
    content problems."""

    def test_handles_a_minimal_pdf(self) -> None:
        from pathlib import Path

        from app.documents.pdf_index import build_index

        fixture = (
            Path(__file__).parent.parent / "providers" / "alliance" / "fixtures" / "document.pdf"
        )
        index = build_index(fixture.read_bytes())
        assert index.page_count >= 1
        assert isinstance(index.contents, list)

    def test_rejects_a_non_pdf_body(self) -> None:
        from pypdf.errors import PdfReadError

        from app.documents.pdf_index import build_index

        # A non-PDF body must fail loudly here; the API maps it to a
        # provider-content error rather than an empty index.
        with pytest.raises(PdfReadError):
            build_index(b"this is not a pdf at all")
