"""Read callout numbers that a drawing draws but never names.

Two of the provider's CAD pipelines put the callout number in the markup
(`<g id="callout_8">`), and `drawing_callouts` reads it from there. A third
does not: it draws the marker circle and the digits as anonymous outlines,
leaving nothing to parse. Roughly 40% of the IA135 drawings are that kind,
including Drive — the one used for the burner-tube lookup.

So the digits are recognised by shape. Each glyph is flattened to points,
normalised into a 16x16 box, and matched against `glyph_dictionary`. How
that dictionary was built and checked is in
docs/MILESTONE_15/callout-reading.md; the short version is that the digits
of the third typeface were established three independent ways that agree.

The reader is also used where the markup DOES name callouts, as a second
opinion — a real drawing was found with two differently-numbered callout
groups stacked on the same marker, where trusting the markup alone gives a
technician the wrong part number.

Every step fails closed. A glyph that is not clearly one digit, a marker
whose digits do not all read, or a number that is not a row in the parts
table yields no tap target at all.
"""

import logging
import re
from dataclasses import dataclass

from app.providers.alliance.glyph_dictionary import DIGIT_SHAPES, GRID

logger = logging.getLogger(__name__)

_PATH = re.compile(r'<path\b[^>]*\bd="([^"]+)"[^>]*>', re.I)
_CIRCLE = re.compile(r"<circle\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')
_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
_COMMAND = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")
_ARITY = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}

# A callout marker is a small circle. Measured across the IA135 drawings
# they sit around r=9.4 in diagram units; the cap is generous but keeps the
# machine's own circular geometry out.
_MAX_MARKER_DIAMETER = 40.0
# How far from a perfect circle a marker may be, as a fraction of radius.
_ROUNDNESS = 0.12
# Digits sit within this fraction of the marker's radius.
_INSIDE = 0.85
# A glyph further than this from every known digit is not read at all.
_MATCH_LIMIT = 0.45
# …and it must be this much closer to its digit than to any other digit.
_MARGIN = 0.10
_CURVE_SAMPLES = 6


@dataclass(frozen=True)
class ReadCallout:
    """A marker whose number was recognised rather than parsed."""

    reference: str
    x: float
    y: float
    radius: float


def flatten_path(d: str, curve_samples: int = _CURVE_SAMPLES) -> list[tuple[float, float]]:
    """Points along a path. `curve_samples=1` gives just the on-curve anchors."""
    points: list[tuple[float, float]] = []
    x = y = start_x = start_y = 0.0
    last_control: tuple[float, float] | None = None
    position = 0
    command = ""
    while position < len(d):
        match = _COMMAND.search(d, position)
        if match is not None and match.start() == position:
            command = match.group(0)
            position = match.end()
        elif not command:
            break
        following = _COMMAND.search(d, position)
        end = len(d) if following is None else following.start()
        values = [float(v) for v in _NUMBER.findall(d[position:end])]
        position = end

        lower = command.lower()
        relative = command.islower()
        arity = _ARITY.get(lower)
        if arity is None:
            continue
        if lower == "z":
            x, y = start_x, start_y
            points.append((x, y))
            continue
        if arity == 0 or len(values) < arity:
            continue
        for index in range(0, len(values) - arity + 1, arity):
            args = values[index : index + arity]
            if lower in {"m", "l", "t"}:
                x = x + args[0] if relative else args[0]
                y = y + args[1] if relative else args[1]
                points.append((x, y))
                last_control = None
                if lower == "m":
                    if index == 0:
                        start_x, start_y = x, y
                    # Further pairs after a move are implicit line-tos.
                    lower = "l"
                    command = "l" if relative else "L"
            elif lower == "h":
                x = x + args[0] if relative else args[0]
                points.append((x, y))
            elif lower == "v":
                y = y + args[0] if relative else args[0]
                points.append((x, y))
            elif lower in {"c", "s", "q"}:
                if lower == "c":
                    first = (x + args[0], y + args[1]) if relative else (args[0], args[1])
                    second = (x + args[2], y + args[3]) if relative else (args[2], args[3])
                    finish = (x + args[4], y + args[5]) if relative else (args[4], args[5])
                elif lower == "s":
                    first = (
                        (2 * x - last_control[0], 2 * y - last_control[1])
                        if last_control
                        else (x, y)
                    )
                    second = (x + args[0], y + args[1]) if relative else (args[0], args[1])
                    finish = (x + args[2], y + args[3]) if relative else (args[2], args[3])
                else:
                    first = second = (x + args[0], y + args[1]) if relative else (args[0], args[1])
                    finish = (x + args[2], y + args[3]) if relative else (args[2], args[3])
                for step in range(1, curve_samples + 1):
                    t = step / curve_samples
                    u = 1 - t
                    points.append(
                        (
                            u**3 * x
                            + 3 * u**2 * t * first[0]
                            + 3 * u * t**2 * second[0]
                            + t**3 * finish[0],
                            u**3 * y
                            + 3 * u**2 * t * first[1]
                            + 3 * u * t**2 * second[1]
                            + t**3 * finish[1],
                        )
                    )
                last_control = second
                x, y = finish
            else:  # arc: its endpoint is enough for a digit outline
                x = x + args[5] if relative else args[5]
                y = y + args[6] if relative else args[6]
                points.append((x, y))
    return points


def _bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def glyph_signature(points: list[tuple[float, float]]) -> frozenset[int]:
    """Which cells of a GRID x GRID box the outline passes through.

    Scaled by the larger dimension and centred, so aspect ratio survives —
    a '1' must not normalise into an '8'. Position and size drop out, which
    is exactly what varies between instances of the same digit.
    """
    if len(points) < 3:
        return frozenset()
    x0, y0, x1, y1 = _bounds(points)
    width, height = x1 - x0, y1 - y0
    size = max(width, height)
    if size <= 0:
        return frozenset()
    pad_x, pad_y = (size - width) / 2, (size - height) / 2
    return frozenset(
        int(((y - y0 + pad_y) / size) * (GRID - 1)) * GRID
        + int(((x - x0 + pad_x) / size) * (GRID - 1))
        for x, y in points
    )


def _distance(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 1.0
    return 1 - len(a & b) / len(a | b)


def classify_glyph(signature: frozenset[int]) -> str | None:
    """The digit this shape is, or None if that is not clear enough."""
    if not signature:
        return None
    best: dict[str, float] = {
        digit: min(_distance(signature, shape) for shape in shapes)
        for digit, shapes in DIGIT_SHAPES.items()
    }
    ranked = sorted(best.items(), key=lambda item: item[1])
    (digit, closest), (_, runner_up) = ranked[0], ranked[1]
    if closest > _MATCH_LIMIT or runner_up - closest < _MARGIN:
        return None
    return digit


def _markers(svg: str, shapes: list[tuple[str, list[tuple[float, float]]]]):
    """Every callout circle, however it was drawn."""
    found: list[tuple[float, float, float]] = []
    for tag in _CIRCLE.findall(svg):
        attrs = dict(_ATTR.findall(tag))
        try:
            radius = float(attrs["r"])
            if 0 < radius <= _MAX_MARKER_DIAMETER / 2:
                found.append((float(attrs["cx"]), float(attrs["cy"]), radius))
        except (KeyError, ValueError):
            continue
    for _d, points in shapes:
        circle = _circle_from(points)
        if circle is not None:
            found.append(circle)

    # Markers are drawn as concentric pairs; keep one per position.
    unique: list[tuple[float, float, float]] = []
    for cx, cy, radius in sorted(found, key=lambda m: -m[2]):
        if all((cx - ux) ** 2 + (cy - uy) ** 2 > (ur / 2) ** 2 for ux, uy, ur in unique):
            unique.append((cx, cy, radius))
    return unique


def _circle_from(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    if len(points) < 8:
        return None
    x0, y0, x1, y1 = _bounds(points)
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0 or width > _MAX_MARKER_DIAMETER:
        return None
    if abs(width - height) / max(width, height) > _ROUNDNESS:
        return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    radius = (width + height) / 4
    for x, y in points:
        if abs(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - radius) / radius > _ROUNDNESS:
            return None
    return cx, cy, radius


def read_callouts(svg: str) -> list[ReadCallout]:
    """Recognise the number inside every callout marker that reads cleanly."""
    if not svg:
        return []
    shapes: list[tuple[str, list[tuple[float, float]]]] = []
    for d in _PATH.findall(svg):
        points = flatten_path(d)
        if len(points) >= 3:
            shapes.append((d, points))

    glyphs = []
    for _d, points in shapes:
        if _circle_from(points) is not None:
            continue
        x0, y0, x1, y1 = _bounds(points)
        if 0 < x1 - x0 <= _MAX_MARKER_DIAMETER and 0 < y1 - y0 <= _MAX_MARKER_DIAMETER:
            glyphs.append((points, ((x0 + x1) / 2, (y0 + y1) / 2)))

    out: list[ReadCallout] = []
    for cx, cy, radius in _markers(svg, shapes):
        inside = sorted(
            (
                (points, centre)
                for points, centre in glyphs
                if (centre[0] - cx) ** 2 + (centre[1] - cy) ** 2 <= (radius * _INSIDE) ** 2
            ),
            key=lambda item: item[1][0],  # left to right
        )
        if not inside:
            continue
        digits = []
        for points, _centre in inside:
            digit = classify_glyph(glyph_signature(points))
            if digit is None:
                digits = []
                break
            digits.append(digit)
        if not digits or digits[0] == "0":
            continue  # unreadable, or not a callout number
        out.append(ReadCallout("".join(digits), cx, cy, radius))
    return out
