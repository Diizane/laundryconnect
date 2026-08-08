"""Matching a resolved model to its manual generation (Milestone 14).

Pinned against the real BA120N comments and the two serials verified in
the field on 2026-08-08.
"""

import pytest

from app.providers.alliance.generation import (
    best_generation_index,
    parse_generation_rule,
    rule_matches,
)

# Verbatim from the live Alliance response for a BA120N serial search.
BA120N_COMMENTS = [
    "18 Digit Model Numbers with 3 and 5 in 13th Position; D, F or N in 7th Position",
    "Models Through Serial No. 0907000048",
    "15 Digit Model Numbers with 2 in 12th Position",
    "18 Digit Model Numbers with 6 in 13th Position",
]


class TestRealMachines:
    """The two machines whose burner tubes were looked up by hand."""

    @pytest.mark.parametrize(
        ("serial", "model", "expected_index"),
        [
            # 18 chars, position 13 = '3', position 7 = 'N'
            ("1910075972", "BA120NNN0RPC3W0000", 0),
            # 18 chars, position 13 = '6'
            ("2110046166", "BA120NNN0RPC6W0000", 3),
        ],
    )
    def test_picks_the_generation_a_human_would(
        self, serial: str, model: str, expected_index: int
    ) -> None:
        assert best_generation_index(BA120N_COMMENTS, model, serial) == expected_index


class TestRuleParsing:
    def test_digit_length_and_single_position(self) -> None:
        rule = parse_generation_rule("18 Digit Model Numbers with 6 in 13th Position")
        assert rule.digit_length == 18
        assert rule.positions == [(13, {"6"})]

    def test_multiple_values_at_one_position(self) -> None:
        rule = parse_generation_rule("18 Digit Model Numbers with 3 and 5 in 13th Position")
        assert rule.positions == [(13, {"3", "5"})]

    def test_second_clause_after_a_semicolon_is_parsed(self) -> None:
        # The trailing clause has no "with" — missing it would let a model
        # with the wrong 7th character match.
        rule = parse_generation_rule(BA120N_COMMENTS[0])
        assert (13, {"3", "5"}) in rule.positions
        assert (7, {"D", "F", "N"}) in rule.positions

    def test_serial_threshold(self) -> None:
        rule = parse_generation_rule("Models Through Serial No. 0907000048")
        assert rule.serial_through == "0907000048"

    @pytest.mark.parametrize("comment", [None, "", "Date 9/99", "Cabinet Hardmount"])
    def test_unrecognised_prose_yields_an_empty_rule(self, comment: str | None) -> None:
        assert parse_generation_rule(comment).is_empty


class TestRuleMatching:
    def test_wrong_length_fails(self) -> None:
        rule = parse_generation_rule("18 Digit Model Numbers with 6 in 13th Position")
        assert rule_matches(rule, "BA120N", "1910075972") is False

    def test_wrong_character_at_a_constrained_position_fails(self) -> None:
        rule = parse_generation_rule(BA120N_COMMENTS[0])
        # Position 13 is right but position 7 is 'X', not D/F/N.
        assert rule_matches(rule, "BA120NXN0RPC3W0000", "1910075972") is False

    def test_serial_threshold_includes_the_boundary(self) -> None:
        rule = parse_generation_rule("Models Through Serial No. 0907000048")
        assert rule_matches(rule, "ANY", "0907000048") is True
        assert rule_matches(rule, "ANY", "0907000049") is False
        # A modern serial is well past it — this is why the two field
        # machines matched on model position, not on this rule.
        assert rule_matches(rule, "ANY", "1910075972") is False

    def test_non_numeric_serial_is_undecidable_not_a_guess(self) -> None:
        rule = parse_generation_rule("Models Through Serial No. 0907000048")
        assert rule_matches(rule, "ANY", "135RX009281WK") is None

    def test_empty_rule_is_undecidable(self) -> None:
        assert rule_matches(parse_generation_rule("Date 9/99"), "BA120N", "1910075972") is None

    def test_missing_model_is_undecidable(self) -> None:
        rule = parse_generation_rule("18 Digit Model Numbers with 6 in 13th Position")
        assert rule_matches(rule, None, "1910075972") is None


class TestAmbiguityIsNeverGuessed:
    """Showing a technician the wrong manual is worse than showing none, so
    anything other than exactly one match highlights nothing."""

    def test_no_match_highlights_nothing(self) -> None:
        # Position 13 is '9', which no generation covers, and the serial is
        # past the "Models Through Serial No." threshold.
        assert best_generation_index(BA120N_COMMENTS, "BA120NNN0RPC9W0000", "1910075972") is None

    def test_several_matches_highlight_nothing(self) -> None:
        duplicates = [
            "18 Digit Model Numbers with 3 in 13th Position",
            "18 Digit Model Numbers with 3 in 13th Position",
        ]
        assert best_generation_index(duplicates, "BA120NNN0RPC3W0000", "1910075972") is None

    def test_unparseable_comments_highlight_nothing(self) -> None:
        assert best_generation_index(["Date 9/99", "Date 4/01"], "BA120N", "1910075972") is None

    def test_model_search_without_a_resolved_model_highlights_nothing(self) -> None:
        assert best_generation_index(BA120N_COMMENTS, None, None) is None


class TestConnectorAnnotation:
    def test_serial_search_marks_one_generation(self) -> None:
        from app.providers.alliance.connector import _annotate_generation_match

        records = [
            {
                "description": comment,
                "metadata": {
                    "resolved_model": "BA120NNN0RPC6W0000",
                    "resolved_serial": "2110046166",
                },
            }
            for comment in BA120N_COMMENTS
        ]
        _annotate_generation_match(records)
        marked = [i for i, r in enumerate(records) if r["metadata"].get("generation_match")]
        assert marked == [3]

    def test_model_search_marks_nothing(self) -> None:
        from app.providers.alliance.connector import _annotate_generation_match

        # No resolved model/serial: a plain model search must be untouched.
        records = [{"description": c, "metadata": {}} for c in BA120N_COMMENTS]
        _annotate_generation_match(records)
        assert all("generation_match" not in r["metadata"] for r in records)

    def test_single_result_is_left_alone(self) -> None:
        from app.providers.alliance.connector import _annotate_generation_match

        records = [{"description": BA120N_COMMENTS[0], "metadata": {"resolved_model": "X"}}]
        _annotate_generation_match(records)
        assert "generation_match" not in records[0]["metadata"]
