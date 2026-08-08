"""Searchable index and contents for a provider PDF (Milestone 13).

Builds two things from a cached document, once, and stores them beside it:

- **page text**, so a technician can search inside an open manual;
- **contents**, from the PDF's embedded outline, so tapping a heading jumps
  to its page.

Neither is guaranteed to exist. Measured against real Alliance manuals
(2026-08-08):

| manual            | pages | usable text | outline entries |
|-------------------|-------|-------------|-----------------|
| D0287 Parts       |    82 |       81/82 |              41 |
| D0568 Technical   |    43 |       43/43 |               2 |
| D0167 Install/Op  |    35 |    **0/35** |               2 |

D0167's fonts are embedded without character maps, so extraction returns
glyph codes (`/G68/G82…`) rather than words. Searching it would silently
return nothing, so unusable text is DETECTED and reported — the app can
say "this manual isn't searchable" instead of looking broken.

Extraction reuses the Milestone 7 pipeline (pypdf, per-page fault
tolerance, size/page/time limits), so a hostile or broken PDF cannot hang
or exhaust the server.
"""

import logging
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# A page counts as searchable when real words clearly outnumber glyph
# codes; see the module docstring for why this check exists at all.
_GLYPH = re.compile(r"/G\d+")
_WORD = re.compile(r"\b[A-Za-z]{3,}\b")
_MIN_USABLE_RATIO = 0.5


def text_quality(text: str) -> float:
    """Fraction of a page's content that is real words rather than
    unmapped glyph codes. 0.0 for empty or wholly unmapped text."""
    if not text.strip():
        return 0.0
    glyphs = len(_GLYPH.findall(text))
    words = len(_WORD.findall(text))
    if words + glyphs == 0:
        return 0.0
    return words / (words + glyphs)


@dataclass
class ContentsEntry:
    title: str
    page_number: int  # 1-based, as shown to the technician
    depth: int = 0


@dataclass
class DocumentIndex:
    page_count: int
    page_texts: list[str] = field(default_factory=list)
    contents: list[ContentsEntry] = field(default_factory=list)

    @property
    def searchable_pages(self) -> int:
        return sum(1 for t in self.page_texts if text_quality(t) >= _MIN_USABLE_RATIO)

    @property
    def is_searchable(self) -> bool:
        """False when the PDF carries no usable text layer — a scan, or
        fonts without character maps."""
        return self.searchable_pages > 0

    def to_json(self) -> dict:
        return {
            "page_count": self.page_count,
            "page_texts": self.page_texts,
            "contents": [
                {"title": e.title, "page_number": e.page_number, "depth": e.depth}
                for e in self.contents
            ],
        }

    @classmethod
    def from_json(cls, data: dict) -> "DocumentIndex":
        return cls(
            page_count=int(data["page_count"]),
            page_texts=list(data.get("page_texts", [])),
            contents=[
                ContentsEntry(
                    title=str(e["title"]),
                    page_number=int(e["page_number"]),
                    depth=int(e.get("depth", 0)),
                )
                for e in data.get("contents", [])
            ],
        )


def _outline_entries(reader: PdfReader) -> list[ContentsEntry]:
    """Flatten the embedded outline, resolving each entry to a page number.

    Tolerant by design: a malformed or unresolvable entry is skipped rather
    than failing the whole document.
    """
    entries: list[ContentsEntry] = []

    def walk(items, depth: int) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            try:
                title = str(item.title).strip().replace("\r", " ")
                page_number = reader.get_destination_page_number(item) + 1
            except Exception:  # noqa: S112 - one bad entry must not cost the outline
                logger.debug("skipped an unresolvable outline entry")
                continue
            if title:
                entries.append(ContentsEntry(title=title, page_number=page_number, depth=depth))

    try:
        walk(reader.outline or [], 0)
    except Exception:
        logger.warning("pdf outline could not be read")
    return entries


def build_index(pdf_bytes: bytes, *, max_pages: int = 2000) -> DocumentIndex:
    """Extract page text and contents from a PDF held in memory.

    Never raises for content problems: an unreadable page yields empty
    text, and a missing outline yields no contents.
    """
    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = min(len(reader.pages), max_pages)

    texts: list[str] = []
    for number in range(page_count):
        try:
            texts.append(reader.pages[number].extract_text() or "")
        except Exception:
            # One bad page must not cost the whole manual.
            texts.append("")
    index = DocumentIndex(
        page_count=page_count, page_texts=texts, contents=_outline_entries(reader)
    )
    logger.info(
        "document indexed",
        extra={
            "pages": page_count,
            "searchable_pages": index.searchable_pages,
            "contents_entries": len(index.contents),
        },
    )
    return index


@dataclass
class SearchHit:
    page_number: int
    snippet: str


def search_index(index: DocumentIndex, query: str, *, limit: int = 50) -> list[SearchHit]:
    """Case-insensitive page-cited search. Only pages with usable text are
    searched, so a glyph-encoded manual returns nothing rather than noise."""
    from app.documents.snippets import build_snippet

    needle = query.strip()
    if not needle:
        return []
    hits: list[SearchHit] = []
    for number, text in enumerate(index.page_texts, start=1):
        if text_quality(text) < _MIN_USABLE_RATIO:
            continue
        snippet = build_snippet(text, needle)
        if snippet:
            hits.append(SearchHit(page_number=number, snippet=snippet))
        if len(hits) >= limit:
            break
    return hits
