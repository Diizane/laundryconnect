"""API contract tests for provider document discovery + download proxy.

Fully offline (mock provider by default; Alliance in fixture mode where
noted). Proves the client-safe contract: no provider URLs/paths in
responses, opaque tokens that fail closed, deliberate error mapping, and
that the existing search API is unchanged.
"""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentContent,
    ProviderDocumentsUnsupported,
    ProviderForbidden,
    ReauthenticationRequired,
)
from app.providers.mock.connector import MockProviderConnector


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> Iterator[TestClient]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(monkeypatch, ENABLED_PROVIDERS="mock")


@pytest.fixture
def alliance_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _client(monkeypatch, ENABLED_PROVIDERS="alliance", ALLIANCE_MODE="fixture")


def _discover(client: TestClient, provider: str = "mock", ref: str = "SC60") -> dict:
    response = client.get(f"/api/v1/providers/{provider}/documents", params={"ref": ref})
    assert response.status_code == 200, response.text
    return response.json()


PROVIDER_INTERNALS = ("source_path", "/manuals/", "/mock/documents/", "alliancels", "ManualId")


class TestDiscovery:
    def test_mock_discovery_schema(self, client: TestClient) -> None:
        body = _discover(client)
        assert body["provider_id"] == "mock"
        assert len(body["documents"]) == 3
        available = [d for d in body["documents"] if d["available"]]
        unavailable = [d for d in body["documents"] if not d["available"]]
        assert len(available) == 2 and len(unavailable) == 1
        first = available[0]
        # Client-safe metadata fields are present…
        for field in (
            "token",
            "title",
            "document_type",
            "part_number",
            "comment",
            "languages",
            "category",
            "filename",
            "available",
            "data_origin",
        ):
            assert field in first
        assert first["data_origin"] == "mock"  # honest labelling survives the API
        assert first["token"]
        # …and unavailable documents carry NO token.
        assert unavailable[0]["token"] is None

    def test_no_provider_urls_or_paths_in_response(self, client: TestClient) -> None:
        raw = json.dumps(_discover(client))
        for marker in PROVIDER_INTERNALS:
            assert marker not in raw, f"provider internal '{marker}' leaked"

    def test_alliance_fixture_discovery_via_api(self, alliance_client: TestClient) -> None:
        body = _discover(alliance_client, provider="alliance", ref="1001:2002")
        assert body["provider_id"] == "alliance"
        assert len(body["documents"]) == 4
        raw = json.dumps(body)
        for marker in PROVIDER_INTERNALS:
            assert marker not in raw, f"provider internal '{marker}' leaked"
        origins = {d["data_origin"] for d in body["documents"]}
        assert origins == {"fixture"}  # never labelled live

    def test_invalid_reference_is_400(self, alliance_client: TestClient) -> None:
        response = alliance_client.get(
            "/api/v1/providers/alliance/documents", params={"ref": "not-a-valid-ref"}
        )
        assert response.status_code == 400

    def test_url_shaped_reference_rejected_at_the_surface(self, client: TestClient) -> None:
        # The generic ref pattern refuses URL/path characters outright (422
        # from validation) — there is no arbitrary URL/path input surface.
        response = client.get(
            "/api/v1/providers/mock/documents",
            params={"ref": "https://evil.example/steal"},
        )
        assert response.status_code == 422

    def test_unknown_provider_is_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/providers/nope/documents", params={"ref": "SC60"})
        assert response.status_code == 404

    def test_provider_without_capability_is_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def unsupported(self, reference):
            raise ProviderDocumentsUnsupported("mock says no")

        monkeypatch.setattr(MockProviderConnector, "discover_documents", unsupported)
        response = client.get("/api/v1/providers/mock/documents", params={"ref": "SC60"})
        assert response.status_code == 400
        assert "mock says no" not in response.text  # raw exception text never leaks


class TestDownload:
    def test_discover_then_download_round_trip(self, client: TestClient) -> None:
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        response = client.get(f"/api/v1/providers/mock/documents/{token}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")
        assert response.headers["cache-control"] == "no-store"

    def test_filename_header_is_sanitised(self, client: TestClient) -> None:
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        disposition = client.get(f"/api/v1/providers/mock/documents/{token}").headers[
            "content-disposition"
        ]
        assert disposition == 'inline; filename="sc60-service.pdf"'
        assert "/" not in disposition.split("filename=")[1]

    def test_tampered_token_is_404(self, client: TestClient) -> None:
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        version, body, signature = token.split(".")
        flipped = ("A" if body[0] != "A" else "B") + body[1:]
        response = client.get(f"/api/v1/providers/mock/documents/{version}.{flipped}.{signature}")
        assert response.status_code == 404

    def test_malformed_token_is_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/providers/mock/documents/garbage").status_code == 404

    def test_token_bound_to_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for client in _client(
            monkeypatch, ENABLED_PROVIDERS="mock,alliance", ALLIANCE_MODE="fixture"
        ):
            token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
            # A mock-minted token must not resolve against Alliance.
            response = client.get(f"/api/v1/providers/alliance/documents/{token}")
            assert response.status_code == 404

    def test_document_not_found_is_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def missing(self, source_path):
            raise DocumentNotFound("gone")

        monkeypatch.setattr(MockProviderConnector, "fetch_document", missing)
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        assert client.get(f"/api/v1/providers/mock/documents/{token}").status_code == 404

    def test_reauthentication_required_is_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def expired(self, source_path):
            raise ReauthenticationRequired("session material never leaks")

        monkeypatch.setattr(MockProviderConnector, "fetch_document", expired)
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        response = client.get(f"/api/v1/providers/mock/documents/{token}")
        assert response.status_code == 503
        assert "session material" not in response.text

    def test_forbidden_is_502(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def forbidden(self, source_path):
            raise ProviderForbidden("403 from provider")

        monkeypatch.setattr(MockProviderConnector, "fetch_document", forbidden)
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        assert client.get(f"/api/v1/providers/mock/documents/{token}").status_code == 502

    def test_invalid_document_content_is_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def not_a_pdf(self, source_path):
            raise InvalidDocumentContent("expected content type 'application/pdf'")

        monkeypatch.setattr(MockProviderConnector, "fetch_document", not_a_pdf)
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        response = client.get(f"/api/v1/providers/mock/documents/{token}")
        assert response.status_code == 502

    def test_transient_provider_failure_is_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.providers.errors import ProviderError

        async def flaky(self, source_path):
            raise ProviderError("upstream timeout detail")

        monkeypatch.setattr(MockProviderConnector, "fetch_document", flaky)
        token = next(d["token"] for d in _discover(client)["documents"] if d["token"])
        response = client.get(f"/api/v1/providers/mock/documents/{token}")
        assert response.status_code == 502
        assert "upstream timeout detail" not in response.text


class TestSearchApiUnchanged:
    def test_search_contract_untouched(self, client: TestClient) -> None:
        response = client.post("/api/v1/search", json={"query": "SC60"})
        assert response.status_code == 200
        body = response.json()
        assert {p["provider_id"]: p["status"] for p in body["providers"]} == {"mock": "success"}
        assert body["total_results"] > 0
