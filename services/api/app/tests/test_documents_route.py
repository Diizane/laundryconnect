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


def test_document_detail_includes_page_count(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "SC60 Washer-Extractor Service Manual (sample)"
    assert body["provider"] == "mock"
    assert body["page_count"] == 3
    assert body["source_reference"] == "mock-doc-sc60-service"


def test_document_page_content(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/pages/2")
    assert response.status_code == 200
    body = response.json()
    assert body["page_number"] == 2
    assert "EdL" in body["text_content"]
    assert body["text_content"].startswith("SAMPLE PAGE.")


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
        "hits": [],
    }


def test_in_document_search_query_too_short_422(seeded_client: TestClient) -> None:
    document_id = _service_manual_id(seeded_client)
    response = seeded_client.get(f"/api/v1/documents/{document_id}/search", params={"q": "x"})
    assert response.status_code == 422
