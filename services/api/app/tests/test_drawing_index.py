"""Finding which drawing a part lives in.

Filtering drawing titles cannot answer "where is the drive belt?" — no
title contains the word "belt". These cover the index that can: parsing the
combined print page, searching it, and storing it.
"""

import json
import time
from pathlib import Path

import pytest

from app.documents.drawing_index import (
    DrawingIndex,
    DrawingIndexStore,
    IndexedDrawing,
    IndexedPart,
)
from app.providers.alliance.document_parser import parse_drawings_print

FIXTURE = (
    Path(__file__).parent.parent / "providers" / "alliance" / "fixtures"
) / "drawings_print_page.html"


class TestParsingThePrintPage:
    def sections(self):
        return parse_drawings_print(FIXTURE.read_bytes())

    def test_reads_every_drawing_and_its_parts(self) -> None:
        sections = self.sections()
        assert [s.title for s in sections] == ["Frame", "Drive", "Wire Harnesses"]
        drive = next(s for s in sections if s.title == "Drive")
        assert [(p.reference, p.part_number, p.description) for p in drive.parts] == [
            ("8", "SP533157", "Belt"),
            ("9", "SP533158", "Motor Pulley"),
        ]

    def test_a_drawing_with_no_parts_table_is_still_listed(self) -> None:
        """Its name can still be what someone searches for."""
        harnesses = next(s for s in self.sections() if s.title == "Wire Harnesses")
        assert harnesses.parts == []

    def test_diagrams_are_discarded(self) -> None:
        """The real page is 41 MB because every diagram is inline; only the
        parts lists are wanted, and keeping the rest would not fit in the
        server's memory budget."""
        sections = self.sections()
        assert all("<path" not in part.description for s in sections for part in s.parts)
        assert sum(len(s.parts) for s in sections) == 4

    def test_an_unrecognisable_page_yields_nothing_rather_than_raising(self) -> None:
        assert parse_drawings_print(b"<html><body><p>nope</p></body></html>") == []


def index(*drawings: IndexedDrawing, built_at: float = 1000.0) -> DrawingIndex:
    return DrawingIndex(drawings=tuple(drawings), built_at=built_at)


DRIVE = IndexedDrawing(
    title="Drive",
    parts=(
        IndexedPart(reference="8", part_number="SP533157", description="Belt"),
        IndexedPart(reference="9", part_number="SP533158", description="Motor Pulley"),
    ),
)
FRAME = IndexedDrawing(
    title="Frame",
    parts=(IndexedPart(reference="1", part_number="SP101", description="Frame Weldment"),),
)
BELT_GUARD = IndexedDrawing(
    title="Belt Guard",
    parts=(IndexedPart(reference="3", part_number="SP300", description="Cover"),),
)


class TestSearching:
    def test_finds_the_drawing_a_part_lives_in(self) -> None:
        """The whole point: "belt" is in no drawing title, but it is in
        Drive's parts list."""
        found = index(DRIVE, FRAME).search("belt")
        assert [drawing.title for drawing, _ in found] == ["Drive"]
        assert [part.part_number for _, matched in found for part in matched] == ["SP533157"]

    def test_matches_a_part_number_too(self) -> None:
        found = index(DRIVE).search("SP5331")
        assert [d.title for d, _ in found] == ["Drive"]

    def test_matches_a_callout_number_exactly(self) -> None:
        assert [d.title for d, _ in index(DRIVE).search("8")] == ["Drive"]
        assert index(DRIVE).search("88") == []

    def test_is_case_insensitive_and_ignores_surrounding_space(self) -> None:
        assert [d.title for d, _ in index(DRIVE).search("  BELT ")] == ["Drive"]

    def test_a_title_match_is_kept_even_with_no_matching_part(self) -> None:
        """Someone who knows the drawing's name should not have to
        out-guess the parts list."""
        found = index(BELT_GUARD).search("belt")
        assert [d.title for d, _ in found] == ["Belt Guard"]
        assert found[0][1] == []

    def test_an_exact_part_description_outranks_a_title_match(self) -> None:
        found = index(BELT_GUARD, DRIVE).search("belt")
        assert [d.title for d, _ in found] == ["Drive", "Belt Guard"]

    def test_no_match_yields_nothing(self) -> None:
        assert index(DRIVE, FRAME).search("thermostat") == []

    def test_a_blank_query_yields_nothing(self) -> None:
        assert index(DRIVE).search("   ") == []

    def test_results_are_capped(self) -> None:
        many = [
            IndexedDrawing(
                title=f"Drawing {i}",
                parts=(IndexedPart(reference="1", part_number="X", description="Belt"),),
            )
            for i in range(40)
        ]
        assert len(index(*many).search("belt", limit=5)) == 5


class TestStore:
    def store(self, tmp_path: Path, *, ttl: int = 100, now=lambda: 1000.0):
        return DrawingIndexStore(str(tmp_path), ttl_seconds=ttl, now=now)

    def test_round_trips(self, tmp_path: Path) -> None:
        store = self.store(tmp_path)
        store.put("alliance", "16774:430362", index(DRIVE))
        restored = store.get("alliance", "16774:430362")
        assert restored is not None
        assert restored.drawings[0].parts[0].description == "Belt"

    def test_machines_do_not_share_an_index(self, tmp_path: Path) -> None:
        store = self.store(tmp_path)
        store.put("alliance", "1:1", index(DRIVE))
        assert store.get("alliance", "2:2") is None

    def test_an_index_past_its_life_is_not_used(self, tmp_path: Path) -> None:
        clock = [1000.0]
        store = DrawingIndexStore(str(tmp_path), ttl_seconds=100, now=lambda: clock[0])
        store.put("alliance", "1:1", index(DRIVE, built_at=1000.0))
        clock[0] = 1099.0
        assert store.get("alliance", "1:1") is not None
        clock[0] = 1101.0
        assert store.get("alliance", "1:1") is None

    def test_a_corrupt_file_is_ignored_rather_than_raised(self, tmp_path: Path) -> None:
        store = self.store(tmp_path)
        store.put("alliance", "1:1", index(DRIVE))
        next(tmp_path.glob("*.json")).write_text("{not json")
        assert store.get("alliance", "1:1") is None

    def test_an_unwritable_location_costs_a_rebuild_not_an_error(self, tmp_path: Path) -> None:
        blocked = tmp_path / "file-not-a-dir"
        blocked.write_text("x")
        store = DrawingIndexStore(str(blocked / "inside"), ttl_seconds=100)
        store.put("alliance", "1:1", index(DRIVE))  # must not raise
        assert store.get("alliance", "1:1") is None

    def test_stored_index_is_not_world_readable(self, tmp_path: Path) -> None:
        store = self.store(tmp_path)
        store.put("alliance", "1:1", index(DRIVE))
        path = next(tmp_path.glob("*.json"))
        assert path.stat().st_mode & 0o077 == 0
        assert json.loads(path.read_text())["drawings"][0]["title"] == "Drive"


@pytest.mark.parametrize("query", ["belt", "Belt", "BELT"])
def test_case_does_not_change_the_answer(query: str) -> None:
    assert [d.title for d, _ in index(DRIVE).search(query)] == ["Drive"]


def test_age_is_reported_from_when_it_was_built() -> None:
    assert index(DRIVE, built_at=1000.0).age_seconds(1500.0) == 500.0
    assert index(DRIVE, built_at=time.time() + 10).age_seconds(time.time()) == 0.0
