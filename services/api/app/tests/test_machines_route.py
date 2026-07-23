"""Machine workspace endpoint tests against a seeded SQLite database."""

import uuid

from fastapi.testclient import TestClient


def _machine_id(client: TestClient, model_number: str) -> str:
    response = client.get("/api/v1/machines", params={"model_number": model_number})
    assert response.status_code == 200
    [machine] = response.json()
    return machine["id"]


def test_find_machines_by_model_number(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/machines", params={"model_number": "sc60"})
    assert response.status_code == 200
    [machine] = response.json()
    assert machine["model_number"] == "SC60"
    assert machine["brand"] == "Speed Queen"
    assert machine["manufacturer"] == "Alliance Laundry Systems"
    assert machine["machine_type"] == "washer_extractor"


def test_find_machines_no_match(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/machines", params={"model_number": "ZZZ9"})
    assert response.status_code == 200
    assert response.json() == []


def test_find_machines_requires_model_number(seeded_client: TestClient) -> None:
    assert seeded_client.get("/api/v1/machines").status_code == 422


def test_get_machine_detail(seeded_client: TestClient) -> None:
    machine_id = _machine_id(seeded_client, "SC60")
    response = seeded_client.get(f"/api/v1/machines/{machine_id}")
    assert response.status_code == 200
    assert response.json()["model_number"] == "SC60"


def test_get_machine_unknown_id_404(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/v1/machines/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_machine_invalid_id_422(seeded_client: TestClient) -> None:
    assert seeded_client.get("/api/v1/machines/not-a-uuid").status_code == 422


def test_machine_documents_grouped_by_type(seeded_client: TestClient) -> None:
    machine_id = _machine_id(seeded_client, "SC60")
    response = seeded_client.get(f"/api/v1/machines/{machine_id}/documents")
    assert response.status_code == 200
    body = response.json()

    assert body["machine"]["model_number"] == "SC60"
    types = [category["document_type"] for category in body["categories"]]
    assert types == sorted(types)
    assert set(types) == {"service_manual", "parts_manual", "wiring_diagram"}

    for category in body["categories"]:
        for document in category["documents"]:
            assert document["provider"] == "mock"
            assert document["title"].endswith("(sample)")


def test_machine_documents_unknown_machine_404(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/v1/machines/{uuid.uuid4()}/documents")
    assert response.status_code == 404


def test_machines_503_without_database(client: TestClient) -> None:
    response = client.get("/api/v1/machines", params={"model_number": "SC60"})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Database is not configured."
