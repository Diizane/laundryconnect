"""SessionTransport mechanics — mocked HTTP client only, no live requests."""

import pytest

from app.providers.alliance.ratelimit import RateLimiter
from app.providers.alliance.transport import (
    HostNotAllowed,
    LiveFetchError,
    SessionTransport,
)
from app.providers.errors import ReauthenticationRequired
from app.providers.models import QueryType

ALLOWED = ["portal.alliancels.net"]


class FakeResponse:
    def __init__(self, status_code: int, *, body: object = None, location: str = "") -> None:
        self.status_code = status_code
        self._body = body if body is not None else {"records": []}
        self.headers = {"location": location} if location else {}

    def json(self) -> object:
        return self._body


class FakeClient:
    """Records requests and returns queued responses (or raises)."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.requests: list[str] = []

    async def request(self, method: str, url: str):
        self.requests.append(url)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _transport(client: FakeClient, **kwargs) -> SessionTransport:
    async def _no_sleep(_seconds: float) -> None:
        return None

    return SessionTransport(
        client=client,
        base_url="https://portal.alliancels.net",
        allowed_hosts=ALLOWED,
        rate_limiter=RateLimiter(0, sleep=_no_sleep),  # 0 → no delay in tests
        sleep=_no_sleep,
        **kwargs,
    )


async def test_successful_fetch_returns_records() -> None:
    records = [{"source_reference": "ALS-SC60-SVC", "title": "SC60 Service Manual"}]
    client = FakeClient([FakeResponse(200, body={"records": records})])
    transport = _transport(client)
    assert await transport.search_raw("SC60", QueryType.AUTO) == records
    assert len(client.requests) == 1  # fetches only the requested query


async def test_only_portal_host_is_fetched() -> None:
    client = FakeClient([FakeResponse(200)])
    transport = _transport(client)
    await transport.search_raw("SC60", QueryType.AUTO)
    from urllib.parse import urlparse

    assert urlparse(client.requests[0]).hostname == "portal.alliancels.net"


async def test_off_allowlist_host_is_refused() -> None:
    client = FakeClient([FakeResponse(200)])
    transport = SessionTransport(
        client=client,
        base_url="https://evil.example.com",
        allowed_hosts=ALLOWED,
        rate_limiter=RateLimiter(0),
    )
    with pytest.raises(HostNotAllowed):
        await transport.search_raw("SC60", QueryType.AUTO)
    assert client.requests == []  # never attempted


async def test_401_raises_reauthentication_required() -> None:
    client = FakeClient([FakeResponse(401)])
    with pytest.raises(ReauthenticationRequired):
        await _transport(client).search_raw("SC60", QueryType.AUTO)


async def test_login_redirect_raises_reauthentication_required() -> None:
    client = FakeClient([FakeResponse(302, location="https://portal.alliancels.net/s/login/")])
    with pytest.raises(ReauthenticationRequired):
        await _transport(client).search_raw("SC60", QueryType.AUTO)


async def test_transient_5xx_is_retried_then_succeeds() -> None:
    client = FakeClient([FakeResponse(503), FakeResponse(200, body={"records": []})])
    result = await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert result == []
    assert len(client.requests) == 2  # retried once


async def test_timeout_error_is_retried_then_raises_live_fetch_error() -> None:
    client = FakeClient([TimeoutError(), TimeoutError(), TimeoutError()])
    with pytest.raises(LiveFetchError):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 3  # initial + 2 retries


async def test_auth_failure_is_not_retried() -> None:
    client = FakeClient([FakeResponse(403), FakeResponse(200)])
    with pytest.raises(ReauthenticationRequired):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 1  # no retry on auth failure


async def test_unrecognised_body_yields_empty_records() -> None:
    client = FakeClient([FakeResponse(200, body={"unexpected": "shape"})])
    assert await _transport(client).search_raw("SC60", QueryType.AUTO) == []


async def test_4xx_other_than_auth_raises_live_fetch_error() -> None:
    client = FakeClient([FakeResponse(400)])
    with pytest.raises(LiveFetchError):
        await _transport(client).search_raw("SC60", QueryType.AUTO)
