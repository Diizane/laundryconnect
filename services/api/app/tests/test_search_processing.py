from app.providers.models import DataOrigin, ProviderResult, ResultType
from app.search.processing import deduplicate, group_by_machine, rank


def make_result(**overrides: object) -> ProviderResult:
    defaults: dict[str, object] = {
        "provider_id": "mock",
        "source_reference": "ref-1",
        "result_type": ResultType.DOCUMENT,
        "data_origin": DataOrigin.MOCK,
        "title": "SC60 Service Manual",
        "model": "SC60",
        "manufacturer": "Alliance Laundry Systems",
        "brand": "Speed Queen",
        "relevance_score": 0.5,
    }
    defaults.update(overrides)
    return ProviderResult(**defaults)


class TestDeduplicate:
    def test_same_source_url_collapses_keeping_best_score(self) -> None:
        low = make_result(source_url="https://example.com/doc1", relevance_score=0.3)
        high = make_result(
            source_url="https://example.com/doc1", provider_id="other", relevance_score=0.9
        )
        deduped = deduplicate([low, high])
        assert len(deduped) == 1
        assert deduped[0].relevance_score == 0.9
        assert deduped[0].metadata["duplicates_collapsed"] == "1"

    def test_same_title_model_revision_collapses(self) -> None:
        a = make_result(title="SC60 Service Manual", revision="Rev 4")
        b = make_result(title="  sc60 service manual ", revision="Rev 4", provider_id="other")
        assert len(deduplicate([a, b])) == 1

    def test_different_revisions_kept_separate(self) -> None:
        a = make_result(revision="Rev 3")
        b = make_result(revision="Rev 4")
        assert len(deduplicate([a, b])) == 2

    def test_distinct_results_untouched(self) -> None:
        a = make_result(title="Service Manual")
        b = make_result(title="Parts Manual")
        deduped = deduplicate([a, b])
        assert len(deduped) == 2
        assert all("duplicates_collapsed" not in r.metadata for r in deduped)


class TestRank:
    def test_orders_by_relevance(self) -> None:
        results = [make_result(relevance_score=0.2), make_result(relevance_score=0.8)]
        ranked = rank(results, "manual")
        assert [r.relevance_score for r in ranked] == [0.8, 0.2]

    def test_exact_model_match_outranks_higher_base_score(self) -> None:
        fuzzy = make_result(model="HS-6008", relevance_score=0.6)
        exact = make_result(model="SC60", relevance_score=0.5)
        ranked = rank([fuzzy, exact], "sc60")
        assert ranked[0].model == "SC60"

    def test_exact_part_match_boosted(self) -> None:
        part = make_result(result_type=ResultType.PART, part_number="F8524501", relevance_score=0.5)
        other = make_result(relevance_score=0.6)
        ranked = rank([part, other], "f8524501")
        assert ranked[0].part_number == "F8524501"


class TestGroupByMachine:
    def test_groups_by_model_preserving_rank_order(self) -> None:
        results = [
            make_result(model="SC60", relevance_score=0.9),
            make_result(
                model="HS-6008", manufacturer="Girbau", brand="Girbau", relevance_score=0.8
            ),
            make_result(model="SC60", title="Parts Manual", relevance_score=0.7),
        ]
        groups = group_by_machine(results)
        assert [key[2] for key, _ in groups] == ["SC60", "HS-6008"]
        assert len(groups[0][1]) == 2

    def test_results_without_model_go_to_final_other_group(self) -> None:
        results = [
            make_result(model=None, manufacturer=None, brand=None, relevance_score=0.95),
            make_result(model="SC60", relevance_score=0.5),
        ]
        groups = group_by_machine(results)
        # "other" group always sorts last, even with the best-ranked result.
        assert [key for key, _ in groups] == [
            ("Alliance Laundry Systems", "Speed Queen", "SC60"),
            (None, None, None),
        ]
