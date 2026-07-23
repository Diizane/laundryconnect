import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A test client against a freshly built app in the test environment."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        get_settings.cache_clear()
