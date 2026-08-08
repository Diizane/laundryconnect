"""A machine's drawing parts index, so a search can say where to look.

A technician looking for the drive belt does not know it lives in the
"Drive" drawing — that is the thing they are trying to find out. Filtering
drawing titles cannot answer it, because the word "belt" appears in no
title.

Answering it means knowing every drawing's parts list. Fetching 34 drawing
pages to find out would be slow and heavy on the provider, so the index is
built from the combined print page instead: **one request** covering every
drawing, from which the diagrams are discarded and only the parts lists
kept (41 MB fetched, ~30 KB stored).

The index is a search aid, never a source of truth. It only decides which
drawing to suggest; opening one always fetches it live, so a stale index
can send someone to a drawing whose contents have since changed, but can
never show them stale contents.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexedPart:
    reference: str
    part_number: str
    description: str

    def matches(self, needle: str) -> bool:
        return (
            needle in self.description.lower()
            or needle in self.part_number.lower()
            or needle == self.reference
        )


@dataclass(frozen=True)
class IndexedDrawing:
    title: str
    parts: tuple[IndexedPart, ...]


@dataclass(frozen=True)
class DrawingIndex:
    """Every drawing of one machine, with its parts."""

    drawings: tuple[IndexedDrawing, ...]
    built_at: float

    def age_seconds(self, now: float) -> float:
        return max(0.0, now - self.built_at)

    def search(self, query: str, limit: int = 25) -> list[tuple[IndexedDrawing, list[IndexedPart]]]:
        """Drawings worth opening for this query, best first.

        A title match is listed even with no matching part, because a
        technician who does know the drawing's name should not have to
        out-guess the parts list.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        scored: list[tuple[int, int, IndexedDrawing, list[IndexedPart]]] = []
        for drawing in self.drawings:
            matched = [part for part in drawing.parts if part.matches(needle)]
            title_match = needle in drawing.title.lower()
            if not matched and not title_match:
                continue
            # Exact part descriptions first, then other part matches, then
            # title-only matches.
            exact = any(part.description.lower() == needle for part in matched)
            rank = 0 if exact else (1 if matched else 2)
            scored.append((rank, -len(matched), drawing, matched))
        scored.sort(key=lambda item: (item[0], item[1], item[2].title))
        return [(drawing, matched) for _rank, _count, drawing, matched in scored[:limit]]


def _payload(index: DrawingIndex) -> dict:
    return {
        "built_at": index.built_at,
        "drawings": [
            {
                "title": drawing.title,
                "parts": [
                    [part.reference, part.part_number, part.description] for part in drawing.parts
                ],
            }
            for drawing in index.drawings
        ],
    }


def _revive(payload: dict) -> DrawingIndex:
    return DrawingIndex(
        built_at=float(payload["built_at"]),
        drawings=tuple(
            IndexedDrawing(
                title=entry["title"],
                parts=tuple(
                    IndexedPart(reference=row[0], part_number=row[1], description=row[2])
                    for row in entry["parts"]
                ),
            )
            for entry in payload["drawings"]
        ),
    )


class DrawingIndexStore:
    """Disk-backed store, one file per machine.

    Failures are never fatal: an index that cannot be read or written costs
    a rebuild, not a broken search.
    """

    def __init__(self, root: str, *, ttl_seconds: int, now=time.time) -> None:
        self._root = Path(root).expanduser()
        self._ttl = ttl_seconds
        self._now = now

    def _path(self, provider_id: str, reference: str) -> Path:
        key = hashlib.sha256(f"{provider_id}\0{reference}".encode()).hexdigest()
        return self._root / f"{key}.json"

    def get(self, provider_id: str, reference: str) -> DrawingIndex | None:
        path = self._path(provider_id, reference)
        try:
            index = _revive(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError, IndexError):
            return None
        if index.age_seconds(self._now()) > self._ttl:
            return None
        return index

    def put(self, provider_id: str, reference: str, index: DrawingIndex) -> None:
        path = self._path(provider_id, reference)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(_payload(index)))
            os.chmod(temporary, 0o600)
            temporary.replace(path)
        except OSError as error:
            # Losing the index costs a rebuild; it must not cost the search.
            logger.warning(
                "drawing index could not be stored",
                extra={"error": type(error).__name__},
            )
