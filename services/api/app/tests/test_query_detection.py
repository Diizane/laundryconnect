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


class TestRealAllianceIdentifiers:
    """Pinned to identifiers actually seen in this project, so a future
    tweak cannot silently re-break serial routing."""

    @pytest.mark.parametrize(
        "serial",
        [
            "135RX009281WK",  # IA135 — was misread as a part number
            "1910075972",  # BA120N
            "2110046166",  # BA120N
        ],
    )
    def test_real_serials_detect_as_serial(self, serial: str) -> None:
        assert detect_query_type(serial, QueryType.AUTO) == QueryType.SERIAL

    @pytest.mark.parametrize(
        "part",
        ["SP533157", "M412025P", "SP309933001020"],
    )
    def test_letter_led_part_numbers_stay_parts(self, part: str) -> None:
        # Alliance part numbers start with letters; serials start with digits.
        assert detect_query_type(part, QueryType.AUTO) == QueryType.PART

    @pytest.mark.parametrize("model", ["DR75", "BA120N", "SC60"])
    def test_short_models_stay_models(self, model: str) -> None:
        assert detect_query_type(model, QueryType.AUTO) == QueryType.MODEL

    @pytest.mark.parametrize("model", ["IAY135J", "IAY135JQEM11B0C0AA"])
    def test_long_model_strings_are_not_serials(self, model: str) -> None:
        """What matters is that they do not route to the serial endpoint.

        A resolved model like IAY135J classifies as a part number, which is
        harmless: for Alliance only SERIAL changes the endpoint, and every
        other type uses the same model search.
        """
        assert detect_query_type(model, QueryType.AUTO) != QueryType.SERIAL

    def test_short_digits_with_letters_are_not_serials(self) -> None:
        # Below serial length, a digits-first alphanumeric is a part.
        assert detect_query_type("1A2B3C4", QueryType.AUTO) == QueryType.PART

    def test_an_explicit_type_always_wins(self) -> None:
        # The ambiguity between long all-digit part numbers and serials is
        # unresolvable by heuristic, so a caller can always override.
        assert detect_query_type("44315101", QueryType.PART) == QueryType.PART
        assert detect_query_type("SP533157", QueryType.SERIAL) == QueryType.SERIAL
