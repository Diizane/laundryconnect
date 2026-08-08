"""Parse the two bounded intermediate pages of the Alliance document workflow.

Milestone 9 Phase 1 established (by supervised observation, 2026-07-26) that
a search result's `/en/Manual?...` link serves an HTML menu page — never the
document — and that manuals/literature are listed on `/en/Model/Literature`
with per-document links to stable PDF paths `/manuals/<Category>/<Part>.pdf`
(query string is a cache-buster, stripped here). Traversal is bounded: at
most those two pages, then one PDF. These parsers extract links and metadata
from each page; they never fetch anything.

Pinned against reconstructed, sanitised fixtures mirroring the observed DOM.
Tolerant: missing/unrecognised structure yields empty results, not errors.
"""

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, urlparse

from bs4 import BeautifulSoup

from app.providers.alliance.drawing_callouts import DrawingCallout, extract_geometry
from app.providers.alliance.svg_style import inline_stylesheet

logger = logging.getLogger(__name__)

_LITERATURE_PREFIX = "/en/Model/Literature"
_DRAWINGS_PRINT_PREFIX = "/en/Manual/DrawingsPrint"
_DOCUMENT_PREFIX = "/manuals/"
_DRAWING_PREFIX = "/en/Manual/Drawing"

# Intermediate-page links carry a mix of FUNCTIONAL parameters (the portal
# 500s without ManualId/ModelId — found by live validation) and echo
# parameters (SearchString, SearchAction, Comment, show…) that repeat the
# operator's search input. Only the functional identifiers are kept; echoes
# are never stored or logged. Document (/manuals/) links keep no query at
# all — Phase 1 verified their only parameter is a cache-buster.
_FUNCTIONAL_PARAMS = ("ManualId", "ModelId")


def _clean_path(href: str) -> str:
    """Provider-relative path only — query strings (cache-busters, session
    echoes) are never kept or logged."""
    parsed = urlparse(href)
    return parsed.path


def _functional_path_with(href: str, names: tuple[str, ...]) -> str:
    """Path plus only the named query parameters, in the given order."""
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    kept = [
        f"{name}={quote(params[name][0], safe='')}"
        for name in names
        if params.get(name) and params[name][0]
    ]
    return f"{parsed.path}?{'&'.join(kept)}" if kept else parsed.path


def _functional_path(href: str) -> str:
    """Provider-relative path plus ONLY the allowlisted functional query
    parameters (catalog identifiers, not account or search data)."""
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    kept = [
        f"{name}={quote(params[name][0], safe='')}"
        for name in _FUNCTIONAL_PARAMS
        if params.get(name) and params[name][0]
    ]
    if not kept:
        return parsed.path
    return f"{parsed.path}?{'&'.join(kept)}"


@dataclass
class DrawingLink:
    """One assembly drawing offered for a model."""

    title: str
    source_path: str
    drawing_id: str | None = None


@dataclass
class ManualPage:
    """What the `/en/Manual` menu page links to (first traversal hop)."""

    literature_path: str | None = None
    drawings_print_path: str | None = None
    direct_pdf_paths: list[str] = field(default_factory=list)
    drawings_available: bool = True
    drawings: list[DrawingLink] = field(default_factory=list)


def parse_manual_page(body: bytes) -> ManualPage:
    soup = BeautifulSoup(body, "html.parser")
    page = ManualPage()
    page.drawings_available = (
        "assembly drawings are not available" not in soup.get_text(" ").lower()
    )
    # Assembly drawings: one row per drawing, its name in the row text.
    seen_drawings: set[str] = set()
    for row in soup.find_all("tr"):
        if row.find("table") is not None:
            # A layout wrapper row "contains" the whole inner table, so its
            # text is every drawing name concatenated. Same trap the
            # literature parser hit in production.
            continue
        anchor = row.find("a", href=lambda h: h and h.startswith(_DRAWING_PREFIX))
        if anchor is None:
            continue
        href = anchor.get("href") or ""
        path = _functional_path_with(href, ("DrawingId", "ManualId", "ModelId", "Index"))
        if path in seen_drawings:
            continue
        seen_drawings.add(path)
        title = " ".join(row.get_text(" ").split())
        # Strip the link's own label, leaving the drawing's name.
        title = title.replace("Click to view drawing.", "").strip()
        drawing_id = (parse_qs(urlparse(href).query).get("DrawingId") or [None])[0]
        page.drawings.append(
            DrawingLink(title=title or "Drawing", source_path=path, drawing_id=drawing_id)
        )

    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        if href.startswith(_LITERATURE_PREFIX) and page.literature_path is None:
            page.literature_path = _functional_path(href)
        elif href.startswith(_DRAWINGS_PRINT_PREFIX) and page.drawings_print_path is None:
            page.drawings_print_path = _functional_path(href)
        elif _DOCUMENT_PREFIX in href and href.split("?", 1)[0].endswith(".pdf"):
            path = _clean_path(href)
            if path not in page.direct_pdf_paths:
                page.direct_pdf_paths.append(path)
    if page.literature_path is None and not page.direct_pdf_paths:
        logger.warning("alliance manual page: no literature or document links found")
    return page


def parse_literature_page(body: bytes) -> list[dict]:
    """Extract the document list (second traversal hop) with its metadata.

    Each record: part_number, document_type, comment, languages, source_path
    (query-stripped), category and filename (from the path), available.
    Rows listed without a PDF link are still returned (available=False) so a
    future document picker can show them honestly.
    """
    soup = BeautifulSoup(body, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        if candidate.find("a", href=lambda h: h and _DOCUMENT_PREFIX in h):
            table = candidate
            break
        header = candidate.find("tr")
        if header and "part #" in header.get_text(" ").strip().lower():
            table = candidate
            break
    if table is None:
        logger.warning("alliance literature page: no document table found")
        return []

    records: list[dict] = []
    for row in table.find_all("tr"):
        if row.find("table") is not None:
            # Production nests the document table inside outer layout tables
            # (found by live validation): a wrapper row "contains" the whole
            # inner table and would otherwise parse as one giant bogus record.
            continue
        cells = row.find_all("td")
        if len(cells) < 4:
            continue  # header or layout row
        part_number = cells[0].get_text(strip=True)
        document_type = cells[1].get_text(strip=True)
        if not part_number or not document_type:
            continue
        comment = cells[2].get_text(strip=True)
        languages = [
            lang.strip().rstrip(".")
            for lang in cells[3].get_text(strip=True).split(",")
            if lang.strip().rstrip(".")
        ]

        anchor = row.find(
            "a", href=lambda h: h and _DOCUMENT_PREFIX in h and h.split("?", 1)[0].endswith(".pdf")
        )
        source_path = _clean_path(anchor.get("href", "")) if anchor else ""
        category: str | None = None
        filename: str | None = None
        if source_path:
            segments = [s for s in source_path.split("/") if s]
            # /manuals/<Category>/<Filename>.pdf
            if len(segments) >= 3 and segments[0] == "manuals":
                category = segments[1]
                filename = segments[-1]

        records.append(
            {
                "part_number": part_number,
                "document_type": document_type,
                "comment": comment or None,
                "languages": languages,
                "source_path": source_path,
                "category": category,
                "filename": filename,
                "available": bool(source_path),
                "title": f"{part_number} — {document_type}",
            }
        )
    return records


@dataclass
class DrawingPart:
    """One row of an assembly drawing's parts table."""

    reference: str
    part_number: str
    description: str
    comments: str | None = None


@dataclass
class DrawingContent:
    """A rendered assembly drawing: the diagram, its parts list, and the
    callout markers that tie the two together."""

    svg: str
    parts: list[DrawingPart] = field(default_factory=list)
    callouts: list[DrawingCallout] = field(default_factory=list)
    view_box: tuple[float, float, float, float] | None = None

    @property
    def has_diagram(self) -> bool:
        return bool(self.svg)


# Drawing pages carry several inline SVGs: the diagram plus the zoom-control
# icons. The diagram used to be identified by a width in inches, but the
# portal exports drawings from more than one CAD pipeline: measured across
# the 34 IA135 drawings, widths were "7.74in", "13.63cm", "502.941px" or
# absent altogether, and that rule found a diagram on only 14 of them.
#
# What does separate them cleanly is how much geometry they contain. In the
# same measurement the diagrams held 22–6,526 drawing elements while no
# icon held more than 2, so the threshold below sits in a wide empty gap
# rather than on a boundary. Group ids are NOT used: they vary too
# ("parts"/"callouts" in one pipeline, a bare "Layer_1" in another).
_MIN_DIAGRAM_ELEMENTS = 10

_SVG_OPEN = re.compile(r"<svg\b[^>]*>", re.I)
_SVG_CLOSE = re.compile(r"</svg\s*>", re.I)
_DRAWING_ELEMENT = re.compile(r"<(?:path|polyline|polygon)\b", re.I)


def _svg_blocks(text: str) -> list[str]:
    """Every balanced top-level <svg>…</svg> block, in document order.

    Balanced rather than shortest-match: a non-greedy regex would truncate
    a diagram at the first nested </svg>.
    """
    events = sorted(
        [(m.start(), 0, m) for m in _SVG_OPEN.finditer(text)]
        + [(m.start(), 1, m) for m in _SVG_CLOSE.finditer(text)]
    )
    blocks: list[str] = []
    depth = 0
    start = 0
    for _position, kind, match in events:
        if kind == 0:
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                blocks.append(text[start : match.end()])
    return blocks


def extract_diagram(text: str) -> str:
    """The one SVG on a drawing page that is the diagram, or "" if unclear.

    Fail closed on ambiguity: showing the wrong diagram would put a
    technician on the wrong assembly, which is worse than showing none.
    """
    candidates = [
        block
        for block in _svg_blocks(text)
        if len(_DRAWING_ELEMENT.findall(block)) >= _MIN_DIAGRAM_ELEMENTS
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            "alliance drawing page: several diagram candidates, showing none",
            extra={"candidates": len(candidates)},
        )
    return ""


def parse_drawing_page(body: bytes) -> DrawingContent:
    """Extract the diagram and its parts table from a drawing page.

    The diagram is vector (SVG), which is why it can be shown and zoomed on
    a phone. Its callout markers carry their own reference numbers in the
    markup, so they are extracted too and the app can turn a tap into a
    part — see docs/MILESTONE_15/drawings-discovery.md. Tolerant: a missing
    diagram or table yields empty values rather than an error.
    """
    text = body.decode("utf-8", "ignore")
    svg = extract_diagram(text)
    if not svg:
        logger.warning("alliance drawing page: no diagram found")
    else:
        # The app's renderer ignores CSS, so a class-styled drawing would
        # arrive as a black silhouette. See svg_style.
        svg = inline_stylesheet(svg)

    soup = BeautifulSoup(body, "html.parser")
    parts: list[DrawingPart] = []
    for row in soup.find_all("tr"):
        if row.find("table") is not None:
            continue  # layout wrapper, not a parts row
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        reference = cells[0].get_text(strip=True)
        # Parts rows start with the callout reference number.
        if not reference.isdigit():
            continue
        parts.append(
            DrawingPart(
                reference=reference,
                part_number=cells[1].get_text(strip=True),
                description=cells[2].get_text(strip=True),
                comments=(cells[3].get_text(strip=True) or None) if len(cells) > 3 else None,
            )
        )
    geometry = extract_geometry(svg)
    references = {part.reference for part in parts}
    # A marker whose number has no row in the parts table cannot tell a
    # technician anything, and would be a tap target that answers wrongly.
    callouts = [callout for callout in geometry.callouts if callout.reference in references]
    if len(callouts) != len(geometry.callouts):
        logger.warning(
            "alliance drawing: callouts without a parts row were dropped",
            extra={"dropped": len(geometry.callouts) - len(callouts)},
        )
    return DrawingContent(svg=svg, parts=parts, callouts=callouts, view_box=geometry.view_box)


@dataclass
class DrawingSection:
    """One drawing's title and parts list, from the combined print page."""

    title: str
    parts: list[DrawingPart] = field(default_factory=list)


# The print page carries every diagram inline, which makes it enormous
# (41 MB for the IA135) while the part of it we want is a few hundred
# kilobytes. Dropping the diagrams before parsing turns it into something a
# small server can handle.
_INLINE_SVG = re.compile(r"<svg\b.*?</svg\s*>", re.S | re.I)


def parse_drawings_print(body: bytes) -> list[DrawingSection]:
    """Every drawing's parts list from `/en/Manual/DrawingsPrint`.

    One request answers what would otherwise be one request per drawing,
    which is why searching parts across a machine is affordable at all. A
    section without a parts table is still returned, so a title-only match
    remains possible.
    """
    text = _INLINE_SVG.sub("", body.decode("utf-8", "ignore"))
    soup = BeautifulSoup(text, "html.parser")
    sections: list[DrawingSection] = []
    for heading in soup.find_all("h4"):
        title = " ".join(heading.get_text(" ").split())
        if not title:
            continue
        table = heading.find_next("table", class_="list")
        parts: list[DrawingPart] = []
        if table is not None:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                reference = cells[0].get_text(strip=True)
                if not reference.isdigit():
                    continue
                parts.append(
                    DrawingPart(
                        reference=reference,
                        part_number=cells[1].get_text(strip=True),
                        description=cells[2].get_text(strip=True),
                        comments=(
                            (cells[3].get_text(strip=True) or None) if len(cells) > 3 else None
                        ),
                    )
                )
        sections.append(DrawingSection(title=title, parts=parts))
    if not sections:
        logger.warning("alliance drawings print page: no drawing sections found")
    return sections
