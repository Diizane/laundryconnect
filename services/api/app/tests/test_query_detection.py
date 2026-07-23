import pytest

from app.providers.models import QueryType
from app.search.detection import detect_query_type


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # Models: short alphanumerics, dashed alphanumerics
        ("SC60", QueryType.MODEL),
        ("HS-6008", QueryType.MODEL),
        ("UW65-PV", QueryType.MODEL),
        # Parts: long letter+digit strings without separators
        ("F8524501", QueryType.PART),
        ("70298701P", QueryType.PART),
        # Serials: long digit-only strings
        ("2100047", QueryType.SERIAL),
        ("210004712345", QueryType.SERIAL),
        # Fault codes: letter-prefixed short numeric codes
        ("E13", QueryType.FAULT_CODE),
        ("F07", QueryType.FAULT_CODE),
        ("e-13", QueryType.FAULT_CODE),
        ("F:2", QueryType.FAULT_CODE),
        # Keywords: anything with spaces, short digits, long words
        ("door lock error", QueryType.KEYWORD),
        ("bearing replacement", QueryType.KEYWORD),
        ("123", QueryType.KEYWORD),
        ("troubleshooting-procedures", QueryType.KEYWORD),
    ],
)
def test_auto_detection(query: str, expected: QueryType) -> None:
    assert detect_query_type(query, QueryType.AUTO) == expected


@pytest.mark.parametrize("requested", [t for t in QueryType if t != QueryType.AUTO])
def test_explicit_type_always_wins(requested: QueryType) -> None:
    # Even a query that looks like a serial keeps the explicitly chosen type.
    assert detect_query_type("2100047", requested) == requested
