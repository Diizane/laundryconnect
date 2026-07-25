"""Alliance transports: how raw provider records are obtained per mode.

`FixtureTransport` (default) reads sanitised local fixtures and makes no
network request. The live transport is intentionally NOT implemented while
the access decision record is UNKNOWN — see `connector.py`, which gates any
live path and never reaches a live fetch.
"""

import json
from pathlib import Path
from typing import Protocol

from app.providers.models import QueryType

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Which fields a query matches against, per query type (AUTO/KEYWORD: all).
_FIELDS_BY_QUERY_TYPE: dict[QueryType, tuple[str, ...]] = {
    QueryType.MODEL: ("model",),
    QueryType.SERIAL: ("serial_range",),
    QueryType.PART: ("part_number",),
    QueryType.FAULT_CODE: ("title", "description"),
}


class AllianceTransport(Protocol):
    async def search_raw(self, query: str, query_type: QueryType) -> list[dict]: ...


class FixtureTransport:
    """Serves sanitised fixture records; no network access."""

    def __init__(self, fixtures_dir: Path = _FIXTURES_DIR) -> None:
        self._records = json.loads((fixtures_dir / "search.json").read_text())["records"]

    async def search_raw(self, query: str, query_type: QueryType) -> list[dict]:
        needle = query.strip().lower()
        if not needle:
            return []
        fields = _FIELDS_BY_QUERY_TYPE.get(query_type)
        matches = []
        for record in self._records:
            haystacks = (
                [record.get(field) for field in fields]
                if fields
                else [
                    record.get("title"),
                    record.get("description"),
                    record.get("model"),
                    record.get("part_number"),
                    record.get("brand"),
                    record.get("manufacturer"),
                ]
            )
            if any(needle in str(value).lower() for value in haystacks if value):
                matches.append(record)
        return matches
