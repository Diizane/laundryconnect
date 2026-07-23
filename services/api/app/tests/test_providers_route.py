from fastapi.testclient import TestClient

from app.providers.mock.connector import MockProviderConnector
from app.providers.registry import ProviderRegistry


def test_providers_status(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert len(providers) == 1
    mock = providers[0]
    assert mock["provider_id"] == "mock"
    assert mock["display_name"] == "Mock Provider (sample data)"
    assert mock["data_origin"] == "mock"
    assert mock["enabled"] is True
    assert mock["status"] == "ok"
    assert mock["latency_ms"] is not None


def test_providers_status_never_exposes_credential_fields(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")
    body = response.text.lower()
    for forbidden in ("password", "secret", "token", "cookie", "credential"):
        assert forbidden not in body


def test_providers_status_reports_failing_provider(client: TestClient) -> None:
    registry = ProviderRegistry()
    registry.register(MockProviderConnector(fail_with=RuntimeError("sensitive detail")))
    client.app.state.provider_registry = registry

    response = client.get("/api/v1/providers/status")
    assert response.status_code == 200
    [mock] = response.json()["providers"]
    assert mock["status"] == "failed"
    assert "sensitive detail" not in response.text


def test_providers_status_reports_disabled_provider(client: TestClient) -> None:
    registry = ProviderRegistry()
    registry.register(MockProviderConnector(), enabled=False)
    client.app.state.provider_registry = registry

    response = client.get("/api/v1/providers/status")
    [mock] = response.json()["providers"]
    assert mock["status"] == "disabled"
    assert mock["enabled"] is False
