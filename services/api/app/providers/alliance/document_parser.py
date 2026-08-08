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
    """A rendered assembly drawing: the diagram plus its parts list."""

    svg: str
    parts: list[DrawingPart] = field(default_factory=list)

    @property
    def has_diagram(self) -> bool:
        return bool(self.svg)


# The diagram is an inline SVG sized in inches (the zoom-control icons are
# small pixel-sized SVGs, so the diagram is identified by its dimensions).
_DIAGRAM_SVG = re.compile(r"<svg[^>]*\bwidth=\"[\d.]+in\"[^>]*>.*?</svg>", re.S | re.I)


def parse_drawing_page(body: bytes) -> DrawingContent:
    """Extract the diagram and its parts table from a drawing page.

    The diagram is vector (SVG), which is why it can be shown and zoomed on
    a phone. Callout numbers inside it are drawn as outlines rather than
    text, so they are NOT interpreted here — see
    docs/MILESTONE_15/drawings-discovery.md. Tolerant: a missing diagram or
    table yields empty values rather than an error.
    """
    text = body.decode("utf-8", "ignore")
    match = _DIAGRAM_SVG.search(text)
    svg = match.group(0) if match else ""
    if not svg:
        logger.warning("alliance drawing page: no diagram found")

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
    return DrawingContent(svg=svg, parts=parts)
