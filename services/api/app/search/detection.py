"""Heuristic query-type detection for `auto` searches.

These are deliberately simple, ordered, transparent rules — not machine
learning. They will misclassify some inputs (e.g. letter-only fault codes
like "EdL" look like model numbers); the detected type is returned in the
search response so the technician can see and correct it. Providers may
additionally broaden narrow queries internally.
"""

import re

from app.providers.models import QueryType

# E13, F07, E-13, F:2 — short letter-prefixed numeric codes.
_FAULT_CODE_RE = re.compile(r"^[EF][-:]?\d{1,3}$", re.IGNORECASE)

# Long, purely numeric strings read as serial numbers.
_SERIAL_MIN_DIGITS = 7

# Long letter+digit strings without separators read as part numbers.
_PART_MIN_LENGTH = 7


def detect_query_type(query: str, requested: QueryType) -> QueryType:
    """Return the effective query type.

    An explicitly requested type always wins; only `auto` is detected.
    """
    if requested != QueryType.AUTO:
        return requested

    q = query.strip()
    if " " in q:
        return QueryType.KEYWORD
    if _FAULT_CODE_RE.match(q):
        return QueryType.FAULT_CODE
    if q.isdigit():
        return QueryType.SERIAL if len(q) >= _SERIAL_MIN_DIGITS else QueryType.KEYWORD
    has_letters = any(c.isalpha() for c in q)
    has_digits = any(c.isdigit() for c in q)
    if "-" in q and has_letters and has_digits:
        # Dashed alphanumerics (HS-6008, UW65-PV) are usually model numbers.
        return QueryType.MODEL
    if has_letters and has_digits and len(q) >= _PART_MIN_LENGTH:
        return QueryType.PART
    if has_letters and len(q) <= 10:
        return QueryType.MODEL
    return QueryType.KEYWORD
