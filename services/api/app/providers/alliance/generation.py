"""Match a resolved model to the right manual generation (Milestone 14).

A serial search returns every manual generation for a model family — four
for a BA120N — distinguished only by free-text comments:

    18 Digit Model Numbers with 3 and 5 in 13th Position; D, F or N in 7th Position
    18 Digit Model Numbers with 6 in 13th Position
    15 Digit Model Numbers with 2 in 12th Position
    Models Through Serial No. 0907000048

The serial search also resolves the exact factory configuration
(`1910075972` → `BA120NNN0RPC3W0000`), which is what those comments
describe. Decoding them by hand is the job this removes: for that serial,
position 13 is `3` and position 7 is `N`, so the first manual applies.

**Ranking, never filtering.** These are heuristics over provider prose, and
showing a technician the wrong manual is a safety problem. So a confident
match is only ever *highlighted* — every generation stays listed and
openable. A wrong guess costs an unhelpful ordering, not a wrong procedure.
A match is claimed only when exactly one generation matches; zero or
several means "undetermined" and nothing is highlighted.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DIGIT_LENGTH = re.compile(r"(\d+)\s+Digit\s+Model\s+Numbers", re.I)
# "with 3 and 5 in 13th Position" and, after a semicolon, the same clause
# without the "with": "; D, F or N in 7th Position".
_POSITION = re.compile(
    r"(?:with\s+)?([A-Za-z0-9](?:\s*(?:,|and|or)\s*[A-Za-z0-9])*)\s+"
    r"in\s+(\d+)(?:st|nd|rd|th)\s+Position",
    re.I,
)
_SERIAL_THROUGH = re.compile(r"Models?\s+Through\s+Serial\s+No\.?\s*(\w+)", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass
class GenerationRule:
    """What one manual generation says it covers."""

    digit_length: int | None = None
    # (1-based position within the model number, allowed characters)
    positions: list[tuple[int, set[str]]] = field(default_factory=list)
    serial_through: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.digit_length is None and not self.positions and self.serial_through is None


def parse_generation_rule(comment: str | None) -> GenerationRule:
    """Extract constraints from a manual's comment. Unrecognised prose
    yields an empty rule, which never claims a match."""
    rule = GenerationRule()
    if not comment:
        return rule

    length = _DIGIT_LENGTH.search(comment)
    if length:
        rule.digit_length = int(length.group(1))

    for values, position in _POSITION.findall(comment):
        allowed = {token.upper() for token in _TOKEN.findall(values)}
        # "and"/"or" are separators, not values.
        allowed -= {"AND", "OR"}
        if allowed:
            rule.positions.append((int(position), allowed))

    through = _SERIAL_THROUGH.search(comment)
    if through:
        rule.serial_through = through.group(1)

    return rule


def rule_matches(rule: GenerationRule, model: str | None, serial: str | None) -> bool | None:
    """True/False when the rule can be decided, None when it cannot.

    Undecidable cases (no rule parsed, no resolved model, a serial that is
    not comparable) deliberately return None rather than guessing.
    """
    if rule.is_empty:
        return None

    if rule.serial_through is not None:
        if not serial:
            return None
        # Only compare like with like: these thresholds are numeric.
        if not (serial.isdigit() and rule.serial_through.isdigit()):
            return None
        return int(serial) <= int(rule.serial_through)

    if not model:
        return None
    candidate = model.strip().upper()

    if rule.digit_length is not None and len(candidate) != rule.digit_length:
        return False
    for position, allowed in rule.positions:
        if position < 1 or position > len(candidate):
            return False
        if candidate[position - 1] not in allowed:
            return False
    return True


def best_generation_index(
    comments: list[str | None], model: str | None, serial: str | None
) -> int | None:
    """Index of the single generation matching this machine, or None.

    Returns None when nothing matches OR when several do — an ambiguous
    guess is worse than none, because the technician would trust it.
    """
    matches = [
        index
        for index, comment in enumerate(comments)
        if rule_matches(parse_generation_rule(comment), model, serial) is True
    ]
    if len(matches) != 1:
        if matches:
            logger.info(
                "several manual generations matched; not highlighting one",
                extra={"match_count": len(matches)},
            )
        return None
    return matches[0]
