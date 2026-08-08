"""Reading callout numbers that a drawing draws but never names.

The glyph paths here are copied verbatim from real IA135 drawings, one per
typeface, so these exercise the shipped dictionary rather than a fixture of
its own making.
"""

import re

import pytest

from app.providers.alliance.drawing_callouts import DrawingCallout, reconcile
from app.providers.alliance.glyph_reader import (
    ReadCallout,
    classify_glyph,
    flatten_path,
    glyph_signature,
    read_callouts,
)

# "1" and "2" from the typeface that does NOT label its callouts — Drive,
# Serial Label and eleven others.
ONE_UNNAMED = (
    "M25.54,159.74h-1.37v-5.17c-.5.47-1.09.82-1.77,1.04v-1.25c.36-.12.75-.34,1.17-.67s.71-.71."
    "86-1.15h1.11v7.19Z"
)
# "1" from one of the typefaces that does label them.
ONE_NAMED = "M129.01,205.69h.24c1.62,0,2.05-.84,2.09-1.48h1.38v8.52h-1.68v-5.87h-2.03v-1.18Z"
# A marker circle drawn as four arcs, and the same thing as an element.
MARKER_PATH = (
    "M68.58,573.97c5.2,0,9.41,4.21,9.41,9.41s-4.21,9.41-9.41,9.41-9.41-4.21-9.41-9.41,"
    "4.21-9.41,9.41-9.41Z"
)


_OPENING_MOVE = re.compile(r"^M(-?[\d.]+),(-?[\d.]+)")


def at(path: str, x: float, y: float) -> str:
    """The same glyph moved to (x, y).

    Everything after the opening move is relative in these exports, so
    rewriting that one pair translates the whole shape.
    """
    return _OPENING_MOVE.sub(f"M{x},{y}", path, count=1)


class TestGlyphRecognition:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [(ONE_UNNAMED, "1"), (ONE_NAMED, "1")],
    )
    def test_reads_a_one_in_either_typeface(self, path: str, expected: str) -> None:
        assert classify_glyph(glyph_signature(flatten_path(path))) == expected

    def test_a_marker_circle_is_not_mistaken_for_a_digit(self) -> None:
        """Round shapes would otherwise be read as 0."""
        assert classify_glyph(glyph_signature(flatten_path(MARKER_PATH))) != "0"

    def test_an_unrecognisable_shape_reads_as_nothing(self) -> None:
        assert classify_glyph(glyph_signature(flatten_path("M0,0 L40,3 L2,9 Z"))) is None

    def test_an_empty_glyph_reads_as_nothing(self) -> None:
        assert classify_glyph(frozenset()) is None

    def test_position_and_size_do_not_change_the_reading(self) -> None:
        """The same digit is exported at different sizes and positions;
        that is the only difference the descriptor must ignore."""
        scaled = [(x * 3 + 100, y * 3 - 40) for x, y in flatten_path(ONE_UNNAMED)]
        assert glyph_signature(scaled) == glyph_signature(flatten_path(ONE_UNNAMED))


class TestReadingAMarker:
    def diagram(self, *digits: str) -> str:
        """A marker at (68.58, 583.38) with the given glyph paths inside."""
        glyphs = "".join(f'<path d="{d}"/>' for d in digits)
        return f'<svg viewBox="0 0 600 700"><path d="{MARKER_PATH}"/>{glyphs}</svg>'

    def test_reads_the_digit_inside_a_marker(self) -> None:
        # Centred on the marker at (68.58, 583.38).
        svg = self.diagram(at(ONE_UNNAMED, 70.0, 587.0))
        assert [(c.reference, round(c.x, 2)) for c in read_callouts(svg)] == [("1", 68.58)]

    def test_a_marker_with_nothing_inside_is_not_a_callout(self) -> None:
        assert read_callouts(self.diagram()) == []

    def test_a_marker_whose_glyph_is_unreadable_yields_nothing(self) -> None:
        assert read_callouts(self.diagram("M66,580 L72,581 L67,586 Z")) == []

    def test_an_empty_diagram_is_not_an_error(self) -> None:
        assert read_callouts("") == []


class TestReconciliation:
    """Where the markup names a callout and the marker shows a number, the
    two are combined. Neither wins by default."""

    def named(self, reference: str, x: float = 10, y: float = 20) -> DrawingCallout:
        return DrawingCallout(reference=reference, x=x, y=y, radius=9)

    def read(self, reference: str, x: float = 10, y: float = 20) -> ReadCallout:
        return ReadCallout(reference=reference, x=x, y=y, radius=9)

    def test_markup_alone_is_used(self) -> None:
        assert [c.reference for c in reconcile([self.named("8")], [])] == ["8"]

    def test_a_read_marker_alone_is_used(self) -> None:
        """This is the whole point: drawings that name nothing become
        tappable."""
        assert [c.reference for c in reconcile([], [self.read("8")])] == ["8"]

    def test_agreement_keeps_the_callout_once(self) -> None:
        assert [c.reference for c in reconcile([self.named("8")], [self.read("8")])] == ["8"]

    def test_contradiction_drops_the_callout(self) -> None:
        assert reconcile([self.named("8")], [self.read("3")]) == []

    def test_stacked_callouts_are_resolved_by_the_marker(self) -> None:
        """A real drawing has callout_20 and callout_21 groups on the same
        circle; the app would answer with whichever was drawn last. The
        digits on the marker settle it."""
        resolved = reconcile([self.named("20"), self.named("21")], [self.read("21")])
        assert [c.reference for c in resolved] == ["21"]

    def test_stacked_callouts_with_no_reading_are_dropped(self) -> None:
        assert reconcile([self.named("20"), self.named("21")], []) == []

    def test_separate_markers_are_kept_apart(self) -> None:
        callouts = reconcile(
            [self.named("1", 10, 20), self.named("2", 300, 400)],
            [self.read("1", 10, 20), self.read("2", 300, 400)],
        )
        assert sorted(c.reference for c in callouts) == ["1", "2"]

    def test_the_same_number_marked_twice_stays_twice(self) -> None:
        callouts = reconcile([self.named("5", 10, 20), self.named("5", 300, 400)], [])
        assert [c.reference for c in callouts] == ["5", "5"]
