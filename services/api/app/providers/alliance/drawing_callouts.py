"""Callout extraction from an assembly drawing's SVG (Milestone 15 Phase 2).

A callout is the numbered circle on an exploded diagram that points at one
row of the parts table. Extracting them lets the app turn a tap on the
diagram into "this is part SP533157, the drive belt".

The numbers are readable from the markup — see
docs/MILESTONE_15/drawings-discovery.md, including the correction to the
first pass, which looked at the glyph outlines and concluded they were not.
Each callout is a group that states its own reference:

    <g id="callout_5" onclick="click('5')">
      <circle id="circle_5" cx="307.98" cy="437.961" r="9.407"/>
      <path id="number_5" d="…"/>
    </g>

Two export pipelines are in use, so both the id spelling and the marker
shape vary; both are handled here. Everything is fail-closed: a callout
whose reference or position cannot be established with confidence is
dropped rather than guessed, because a tap target that reports the wrong
part number sends a technician to order the wrong part.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Group ids are mangled by the export tool when a name repeats
# ("callout_10_1_", "callout_1-2"), so the reference is the leading digits.
_CALLOUT_OPEN = re.compile(r'<g\b[^>]*\bid="callout[_-](\d+)[^"]*"[^>]*>', re.I)
_G_OPEN = re.compile(r"<g\b[^>]*?>", re.I)
_G_CLOSE = re.compile(r"</g\s*>", re.I)
# Both quoting styles occur: onclick="click('5')" and the &apos;-escaped form.
_ONCLICK_REF = re.compile(r"click\((?:&apos;|&#39;|['\"])(\d+)", re.I)
_CIRCLE = re.compile(r"<circle\b[^>]*>", re.I)
_MARKER_PATH = re.compile(r'<path\b[^>]*\bid="circle[^"]*"[^>]*>', re.I)
_ANY_PATH = re.compile(r"<path\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')
_VIEW_BOX = re.compile(r'<svg\b[^>]*\bviewBox\s*=\s*"([^"]+)"', re.I)
_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
_COMMAND = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")

# Parameters consumed per path command; the endpoint is always the last pair
# except for the arc, where it is also the last pair after five modifiers.
_ARITY = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}


@dataclass(frozen=True)
class DrawingCallout:
    """One numbered marker on a diagram, in the SVG's own coordinate space.

    `reference` matches the `reference` column of the parts table. The same
    reference may appear more than once: a part called out in two places
    gets two markers, and both are tappable.
    """

    reference: str
    x: float
    y: float
    radius: float


@dataclass(frozen=True)
class DiagramGeometry:
    """What the app needs to map a tap to a callout."""

    view_box: tuple[float, float, float, float] | None
    callouts: list[DrawingCallout]


def parse_view_box(svg: str) -> tuple[float, float, float, float] | None:
    """The diagram's coordinate space, or None when it declares none."""
    match = _VIEW_BOX.search(svg)
    if match is None:
        return None
    values = [float(value) for value in _NUMBER.findall(match.group(1))]
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        return None
    return (values[0], values[1], values[2], values[3])


def path_anchor_points(d: str) -> list[tuple[float, float]]:
    """The on-curve points of a path — enough for a bounding box.

    Control points are deliberately ignored: the markers are circles drawn
    as four arcs whose anchors sit at the quadrant points, so the anchor
    bounding box is the circle's own. Including control points would
    inflate it and shift nothing useful.
    """
    points: list[tuple[float, float]] = []
    x = y = 0.0
    start_x = start_y = 0.0
    position = 0
    command = ""
    while position < len(d):
        match = _COMMAND.search(d, position)
        chunk_end = len(d) if match is None else match.start()
        if match is not None and match.start() == position:
            command = match.group(0)
            position += 1
            next_match = _COMMAND.search(d, position)
            chunk_end = len(d) if next_match is None else next_match.start()
        elif not command:
            return points  # numbers before any command: not a path we understand
        chunk = [float(value) for value in _NUMBER.findall(d[position:chunk_end])]
        position = chunk_end

        lower = command.lower()
        relative = command.islower()
        arity = _ARITY.get(lower)
        if arity is None:
            continue
        if lower == "z":
            x, y = start_x, start_y
            points.append((x, y))
            continue
        if arity == 0 or len(chunk) < arity:
            continue
        for index in range(0, len(chunk) - arity + 1, arity):
            args = chunk[index : index + arity]
            if lower == "h":
                x = x + args[0] if relative else args[0]
            elif lower == "v":
                y = y + args[0] if relative else args[0]
            else:
                end_x, end_y = args[-2], args[-1]
                x = x + end_x if relative else end_x
                y = y + end_y if relative else end_y
            points.append((x, y))
            if lower == "m":
                if index == 0:
                    start_x, start_y = x, y
                # Subsequent pairs after an M are implicit line-tos.
                lower = "l"
                command = "l" if relative else "L"
    return points


def _group_body(svg: str, start: int) -> str:
    """The text of the <g> beginning at `start`, up to its matching </g>."""
    depth = 0
    position = start
    while position < len(svg):
        opening = _G_OPEN.search(svg, position)
        closing = _G_CLOSE.search(svg, position)
        if closing is None:
            return svg[start:]
        if opening is not None and opening.start() < closing.start():
            depth += 1
            position = opening.end()
            continue
        depth -= 1
        position = closing.end()
        if depth == 0:
            return svg[start:position]
    return svg[start:]


def _marker(body: str) -> tuple[float, float, float] | None:
    """Centre and radius of the callout's circle, in SVG coordinates."""
    circle = _CIRCLE.search(body)
    if circle is not None:
        attrs = dict(_ATTR.findall(circle.group(0)))
        try:
            return (float(attrs["cx"]), float(attrs["cy"]), float(attrs.get("r", 0)) or 0.0)
        except (KeyError, ValueError):
            pass
    path = _MARKER_PATH.search(body) or _ANY_PATH.search(body)
    if path is None:
        return None
    attrs = dict(_ATTR.findall(path.group(0)))
    points = path_anchor_points(attrs.get("d", ""))
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(width, height) / 2)


def extract_callouts(svg: str) -> list[DrawingCallout]:
    """Every callout marker whose number and position are both certain."""
    callouts: list[DrawingCallout] = []
    for match in _CALLOUT_OPEN.finditer(svg):
        body = _group_body(svg, match.start())
        reference = match.group(1)
        handler = _ONCLICK_REF.search(match.group(0))
        if handler is not None and handler.group(1) != reference:
            # The id and the click handler disagree about which part this
            # marker is. One of them is wrong and we cannot tell which.
            logger.warning(
                "alliance drawing: callout id and handler disagree, dropping it",
                extra={"id_reference": reference, "handler_reference": handler.group(1)},
            )
            continue
        marker = _marker(body)
        if marker is None:
            continue
        x, y, radius = marker
        callouts.append(DrawingCallout(reference=reference, x=x, y=y, radius=radius))
    return callouts


def extract_geometry(svg: str) -> DiagramGeometry:
    """Callouts plus the coordinate space they are expressed in.

    Without a viewBox a tap cannot be mapped to diagram coordinates, so the
    callouts are discarded rather than offered against an unknown space.
    """
    view_box = parse_view_box(svg)
    if view_box is None:
        if svg:
            logger.info("alliance drawing: no viewBox, callouts not offered")
        return DiagramGeometry(view_box=None, callouts=[])
    return DiagramGeometry(view_box=view_box, callouts=extract_callouts(svg))
