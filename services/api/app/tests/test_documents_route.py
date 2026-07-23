"""Document endpoint tests against the seeded sample catalog."""

import uuid

from fastapi.testclient import TestClient


def _service_manual_id(client: TestClient) -> str:
    machines = client.get("/api/v1/machines", params={"model_number": "SC60"}).json()
    documents = client.get(f"/api/v1/machines/{machines[0]['id']}/documents").json()
    for category in documents["categories"]:
        if category["document_type"] == "service_manual":
            return category["documents"][0]["id"]
    raise AssertionError("seeded service manual not found")


def test_document_detail_includes_page_count_and_traceability(
    seeded_client: TestClient,
) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "SC60 Washer-Extractor Service Manual (sample)"
    assert body["provider"] == "mock"
    assert body["page_count"] == 3
    assert body["source_reference"] == "mock-doc-sc60-service"
    assert body["origin"] == "seeded_sample"
    assert body["revision"] == "Rev 4"
    assert body["models"] == ["SC60"]


def test_document_page_content(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/pages/2")
    assert response.status_code == 200
    body = response.json()
    assert body["page_number"] == 2
    assert "EdL" in body["text_content"]
    assert body["text_content"].startswith("SAMPLE PAGE.")
    assert body["text_source"] == "seeded_sample"


def test_document_page_out_of_range_404(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/pages/99")
    assert response.status_code == 404


def test_document_unknown_id_404(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert response.status_code == 404


def test_in_document_search_cites_pages(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(
        f"/api/v1/documents/{document_id}/search", params={"q": "door lock"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "door lock"
    assert body["total_hits"] == 2  # fault table page + replacement procedure page

    pages = [hit["page_number"] for hit in body["hits"]]
    assert pages == [2, 3]
    for hit in body["hits"]:
        assert "door lock" in hit["snippet"].lower()
        assert hit["document_title"].endswith("(sample)")
        assert hit["provider"] == "mock"
        assert hit["origin"] == "seeded_sample"
        assert hit["text_source"] == "seeded_sample"
        assert hit["source_reference"] == "mock-doc-sc60-service"
        assert hit["revision"] == "Rev 4"


def test_in_document_search_case_insensitive(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/search", params={"q": "edl"})
    assert response.json()["total_hits"] == 1


def test_in_document_search_no_hits(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(
        f"/api/v1/documents/{document_id}/search", params={"q": "unobtainium"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "document_id": document_id,
        "query": "unobtainium",
        "total_hits": 0,
        "limit": 20,
        "hits": [],
    }


def test_search_limit_bounds_results_but_reports_total(
    seeded_client: TestClient,
) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(
        f"/api/v1/documents/{document_id}/search",
        params={"q": "door lock", "limit": 1},
    )
    body = response.json()
    assert body["limit"] == 1
    assert len(body["hits"]) == 1
    assert body["total_hits"] == 2  # truncation is visible
    assert body["hits"][0]["page_number"] == 2  # deterministic: lowest page first


def test_search_limit_above_maximum_rejected(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(
        f"/api/v1/documents/{document_id}/search",
        params={"q": "door lock", "limit": 999},
    )
    assert response.status_code == 422


def test_search_like_wildcards_are_literal(seeded_client: TestClient) -> None:
    """'%' and '_' in queries must not act as SQL wildcards."""
    document_id = _service_manual_id(seeded_client)
    # '%' would match every page if interpreted as a wildcard.
    response = seeded_client.get(f"/api/v1/documents/{document_id}/search", params={"q": "d%r"})
    assert response.json()["total_hits"] == 0
    response = seeded_client.get(f"/api/v1/documents/{document_id}/search", params={"q": "d__r"})
    assert response.json()["total_hits"] == 0


def test_search_query_whitespace_stripped(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/search", params={"q": "  EdL  "})
    body = response.json()
    assert body["query"] == "EdL"
    assert body["total_hits"] == 1
    assert "EdL" in body["hits"][0]["snippet"]


def test_in_document_search_query_too_short_422(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/search", params={"q": "x"})
    assert response.status_code == 422
