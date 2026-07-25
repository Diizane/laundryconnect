"""Parts Connection HTML parser — pinned against a sanitised SC60 capture."""

from pathlib import Path

from app.providers.alliance.parser import parse_search_html

FIXTURE = Path(__file__).parent / "fixtures" / "alliance_parts_sc60.html"


def _records() -> list[dict]:
    return parse_search_html(FIXTURE.read_bytes())


def test_parses_all_result_rows() -> None:
    records = _records()
    assert [r["model"] for r in records] == ["SC60AC2", "SC60MD2", "SC60PN2"]


def test_first_row_mapped_fully() -> None:
    first = _records()[0]
    assert first["source_reference"] == "als-model-429746"
    assert first["result_type"] == "model"
    assert first["title"] == "SC60AC2"
    assert first["manufacturer"] == "Alliance Laundry Systems"
    assert first["document_type"] == "assembly_drawings"
    assert first["source_url"] == (
        "https://pc.alliancels.net/en/Manual?ManualId=15171&ModelId=429746"
        "&ExcludeFromAD=False&KO=0&SearchAction=StartsWith&SearchString=SC60&show=Assembly"
    )
    assert first["metadata"]["product_type"] == "Washer-Extractors"
    assert first["metadata"]["product_family"] == "Cabinet Hardmount"
    assert first["metadata"]["model_id"] == "429746"
    assert first["metadata"]["manual_id"] == "15171"


def test_manual_comment_becomes_description() -> None:
    second = _records()[1]
    assert second["description"] == "Design Series 6 and all HC40, SC40 and UC40 models"


def test_row_without_family_or_comment_is_tolerated() -> None:
    third = _records()[2]
    assert third["source_reference"] == "als-model-415774"  # ManualId=0, ModelId used
    assert third["description"] is None
    assert "product_family" not in third["metadata"]


def test_no_account_identifier_in_records() -> None:
    # The distributor/account line must never be carried into records.
    blob = repr(_records())
    for leaked in ("ACCOUNT_PLACEHOLDER", "Distributor", "900045"):
        assert leaked not in blob


def test_empty_or_bad_html_yields_no_records() -> None:
    assert parse_search_html(b"<html><body>no table here</body></html>") == []
    assert parse_search_html(b"") == []
