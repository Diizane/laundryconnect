from fastapi.testclient import TestClient

from app.providers.mock.connector import MockProviderConnector
from app.providers.registry import ProviderRegistry


def test_search_by_model_groups_results(client: TestClient) -> None:
    response = client.post("/api/v1/search", json={"query": "SC60"})
    assert response.status_code == 200
    body = response.json()

    assert body["query"] == "SC60"
    assert body["requested_query_type"] == "auto"
    assert body["detected_query_type"] == "model"
    assert body["total_results"] > 0

    [group] = body["groups"]
    assert group["model"] == "SC60"
    assert group["manufacturer"] == "Alliance Laundry Systems"
    for result in group["results"]:
        assert result["data_origin"] == "mock"
        assert result["provider_id"] == "mock"

    [provider] = body["providers"]
    assert provider["provider_id"] == "mock"
    assert provider["status"] == "success"


def test_search_explicit_query_type(client: TestClient) -> None:
    response = client.post("/api/v1/search", json={"query": "F8524501", "query_type": "part"})
    assert response.status_code == 200
    body = response.json()
    assert body["detected_query_type"] == "part"
    assert body["total_results"] == 1


def test_search_no_matches_still_reports_providers(client: TestClient) -> None:
    response = client.post("/api/v1/search", json={"query": "zzz-no-such-thing-999x"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_results"] == 0
    assert body["groups"] == []
    assert body["providers"][0]["status"] == "success"


def test_search_empty_query_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/search", json={"query": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_blank_query_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/search", json={"query": "   "}).status_code == 422


def test_search_overlong_query_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/search", json={"query": "x" * 201}).status_code == 422


def test_search_invalid_query_type_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/search", json={"query": "SC60", "query_type": "telepathy"})
    assert response.status_code == 422


def test_search_missing_body_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/search").status_code == 422


class FailingConnector(MockProviderConnector):
    provider_id = "failing"
    display_name = "Failing provider (test)"


def test_search_partial_provider_failure(client: TestClient) -> None:
    """A failing provider is reported but never fails the search."""
    registry = ProviderRegistry()
    registry.register(MockProviderConnector())
    registry.register(FailingConnector(fail_with=RuntimeError("portal exploded")))
    client.app.state.provider_registry = registry

    response = client.post("/api/v1/search", json={"query": "SC60"})
    assert response.status_code == 200
    body = response.json()

    statuses = {p["provider_id"]: p["status"] for p in body["providers"]}
    assert statuses == {"mock": "success", "failing": "failed"}
    assert body["total_results"] > 0
    assert "portal exploded" not in response.text
