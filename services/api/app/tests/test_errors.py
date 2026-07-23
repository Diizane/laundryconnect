from fastapi.testclient import TestClient


def test_not_found_returns_structured_error(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["error"]
    assert "traceback" not in response.text.lower()


def test_request_id_header_present(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers.get("X-Request-ID")


def test_request_id_header_honoured(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-correlation-id"})
    assert response.headers["X-Request-ID"] == "test-correlation-id"


def test_unhandled_exception_hides_stack_trace(client: TestClient) -> None:
    # Register a deliberately failing route on the app under test.
    app = client.app

    @app.get("/api/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    response = client.get("/api/v1/_boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert "traceback" not in response.text.lower()
