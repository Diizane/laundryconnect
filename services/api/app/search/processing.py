"""Post-fan-out result processing: deduplication, ranking, grouping.

Pure functions over normalised `ProviderResult` lists — no provider-specific
behaviour belongs here.
"""

from collections import defaultdict

from app.providers.models import ProviderResult

# Boost applied when the query exactly matches a result's model or part
# number — an exact identifier match should outrank fuzzy text matches.
_EXACT_MATCH_BOOST = 0.2


def deduplicate(results: list[ProviderResult]) -> list[ProviderResult]:
    """Collapse results that describe the same underlying item.

    Identity is `source_url` when present, otherwise (result_type, model,
    normalised title, revision). The highest-scoring duplicate wins; the
    number of collapsed duplicates is recorded in its metadata so nothing
    disappears silently.
    """
    best: dict[object, ProviderResult] = {}
    collapsed: dict[object, int] = defaultdict(int)

    for result in results:
        key: object = result.source_url or (
            result.result_type,
            result.model or "",
            result.title.strip().lower(),
            result.revision or "",
        )
        collapsed[key] += 1
        current = best.get(key)
        if current is None or result.relevance_score > current.relevance_score:
            best[key] = result

    deduped = []
    for key, result in best.items():
        if collapsed[key] > 1:
            result = result.model_copy(
                update={
                    "metadata": {**result.metadata, "duplicates_collapsed": str(collapsed[key] - 1)}
                }
            )
        deduped.append(result)
    return deduped


def rank(results: list[ProviderResult], query: str) -> list[ProviderResult]:
    """Order results by relevance, boosting exact identifier matches."""
    needle = query.strip().lower()

    def effective_score(result: ProviderResult) -> float:
        score = result.relevance_score
        exact_fields = (result.model, result.part_number)
        if needle and any(value and value.lower() == needle for value in exact_fields):
            score = min(1.0, score + _EXACT_MATCH_BOOST)
        return score

    return sorted(results, key=effective_score, reverse=True)


def group_by_machine(
    results: list[ProviderResult],
) -> list[tuple[tuple[str | None, str | None, str | None], list[ProviderResult]]]:
    """Group ranked results by (manufacturer, brand, model), preserving order.

    Results with no model association land in a final (None, None, None)
    group. Group order follows each group's best-ranked result, so the input
    must already be ranked.
    """
    groups: dict[tuple[str | None, str | None, str | None], list[ProviderResult]] = {}
    for result in results:
        key = (
            (result.manufacturer, result.brand, result.model)
            if result.model
            else (None, None, None)
        )
        groups.setdefault(key, []).append(result)

    ordered = sorted(
        groups.items(),
        key=lambda item: (item[0] == (None, None, None), results.index(item[1][0])),
    )
    return ordered
