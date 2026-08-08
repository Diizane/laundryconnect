"""Milestone 15 Phase 2: callout extraction from a drawing's SVG.

Fixture-only. The markup shapes here are copied from real IA135 drawings —
both export pipelines — because the two differ in id spelling, quoting and
marker shape, and a mapping that works on one and silently misreads the
other would send a technician to the wrong part.
"""

import pytest

from app.providers.alliance.drawing_callouts import (
    extract_callouts,
    extract_geometry,
    parse_view_box,
    path_anchor_points,
)

# From the IA135 "Frame" drawing: a circle drawn as four cubic arcs.
MARKER_PATH = (
    "M68.58,573.97c5.2,0,9.41,4.21,9.41,9.41s-4.21,9.41-9.41,9.41-9.41-4.21-9.41-9.41,"
    "4.21-9.41,9.41-9.41Z"
)

MODERN_CALLOUT = (
    '<g id="callout_8" data-name="callout 8" onclick="click(&apos;8&apos;)">'
    f'<path id="circle_8" d="{MARKER_PATH}"/>'
    '<path id="number_8" d="M68.63,588.24c-2.2,0-2.95-1.43-2.95-2.59Z"/>'
    "</g>"
)

LEGACY_CALLOUT = (
    '<g id="callout_5" onclick="click(\'5\')" onmouseover="over(\'5\')">'
    '<circle id="circle_x005F_5" cx="307.98" cy="437.961" r="9.407"/>'
    '<path id="number_x005F_5_3_" d="M306.788,437.486c0.313-0.216,0.696-0.468,1.524-0.468Z"/>'
    "</g>"
)


def svg(*bodies: str, view_box: str = "0 0 557.49 699.41") -> str:
    inner = "".join(bodies)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">{inner}</svg>'


class TestPathAnchors:
    def test_a_circle_drawn_as_arcs_gives_its_own_bounding_box(self) -> None:
        points = path_anchor_points(MARKER_PATH)
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        assert (min(xs), max(xs)) == pytest.approx((59.17, 77.99))
        assert (min(ys), max(ys)) == pytest.approx((573.97, 592.79))

    def test_absolute_and_relative_commands_agree(self) -> None:
        assert path_anchor_points("M10,10 L20,20") == path_anchor_points("m10,10 l10,10")

    def test_horizontal_and_vertical_shorthands(self) -> None:
        assert path_anchor_points("M0,0 H10 V5") == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]

    def test_repeated_parameters_continue_the_command(self) -> None:
        assert path_anchor_points("M0,0 L1,1 2,2 3,3") == [
            (0.0, 0.0),
            (1.0, 1.0),
            (2.0, 2.0),
            (3.0, 3.0),
        ]

    def test_nonsense_yields_no_points_rather_than_raising(self) -> None:
        assert path_anchor_points("") == []
        assert path_anchor_points("1,2 3,4") == []


class TestViewBox:
    def test_reads_the_coordinate_space(self) -> None:
        assert parse_view_box(svg()) == (0.0, 0.0, 557.49, 699.41)

    @pytest.mark.parametrize("value", ["0 0 100", "0 0 0 100", "0 0 100 0"])
    def test_a_malformed_or_empty_box_is_rejected(self, value: str) -> None:
        assert parse_view_box(svg(view_box=value)) is None


class TestCallouts:
    def test_reads_a_modern_callout(self) -> None:
        callout = extract_callouts(svg(MODERN_CALLOUT))[0]
        assert callout.reference == "8"
        assert (callout.x, callout.y) == pytest.approx((68.58, 583.38))
        assert callout.radius == pytest.approx(9.41)

    def test_reads_a_legacy_callout(self) -> None:
        callout = extract_callouts(svg(LEGACY_CALLOUT))[0]
        assert callout.reference == "5"
        assert (callout.x, callout.y) == pytest.approx((307.98, 437.961))
        assert callout.radius == pytest.approx(9.407)

    @pytest.mark.parametrize(
        ("group_id", "expected"),
        [("callout_10_1_", "10"), ("callout_1-2", "1"), ("callout_2_2_", "2")],
    )
    def test_export_mangled_ids_still_give_the_reference(
        self, group_id: str, expected: str
    ) -> None:
        """The export tool suffixes duplicated names; the reference is the
        leading digits."""
        group = f'<g id="{group_id}"><circle cx="1" cy="2" r="3"/></g>'
        assert extract_callouts(svg(group))[0].reference == expected

    def test_a_reference_marked_twice_gives_two_targets(self) -> None:
        second = LEGACY_CALLOUT.replace('cx="307.98"', 'cx="100"')
        callouts = extract_callouts(svg(LEGACY_CALLOUT, second))
        assert [c.reference for c in callouts] == ["5", "5"]

    def test_a_callout_whose_id_and_handler_disagree_is_dropped(self) -> None:
        """One of the two is wrong and there is no way to tell which, so the
        marker is not offered at all rather than pointing at a part it may
        not be."""
        group = '<g id="callout_5" onclick="click(\'7\')"><circle cx="1" cy="2" r="3"/></g>'
        assert extract_callouts(svg(group)) == []

    def test_a_callout_without_a_marker_is_dropped(self) -> None:
        assert extract_callouts(svg('<g id="callout_5"><title>nothing</title></g>')) == []

    def test_nested_groups_do_not_swallow_the_next_callout(self) -> None:
        wrapped = f'<g id="callouts"><g id="wrapper">{MODERN_CALLOUT}</g>{LEGACY_CALLOUT}</g>'
        assert [c.reference for c in extract_callouts(svg(wrapped))] == ["8", "5"]

    def test_other_groups_are_ignored(self) -> None:
        assert extract_callouts(svg('<g id="parts"><circle cx="1" cy="2" r="3"/></g>')) == []


class TestGeometry:
    def test_callouts_need_a_coordinate_space(self) -> None:
        """Without a viewBox a tap cannot be mapped to diagram coordinates,
        so no targets are offered."""
        no_box = f"<svg>{MODERN_CALLOUT}</svg>"
        geometry = extract_geometry(no_box)
        assert geometry.view_box is None
        assert geometry.callouts == []

    def test_returns_the_space_and_the_callouts_together(self) -> None:
        geometry = extract_geometry(svg(MODERN_CALLOUT, LEGACY_CALLOUT))
        assert geometry.view_box == (0.0, 0.0, 557.49, 699.41)
        assert [c.reference for c in geometry.callouts] == ["8", "5"]

    def test_an_empty_diagram_is_not_an_error(self) -> None:
        assert extract_geometry("").callouts == []
