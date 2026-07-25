"""SessionTransport mechanics — mocked HTTP client only, no live requests."""

import asyncio

import pytest

from app.providers.alliance.ratelimit import RateLimiter
from app.providers.alliance.transport import (
    AccessForbidden,
    HostNotAllowed,
    LiveFetchError,
    ResponseTooLarge,
    SessionTransport,
)
from app.providers.errors import ReauthenticationRequired
from app.providers.models import QueryType

ALLOWED = ["portal.alliancels.net"]


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        body: object = None,
        location: str = "",
        content: bytes = b"",
        content_length: int | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {"records": []}
        self.content = content
        self.headers: dict[str, str] = {}
        if location:
            self.headers["location"] = location
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        if retry_after is not None:
            self.headers["retry-after"] = retry_after

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


async def _no_sleep(_seconds: float) -> None:
    return None


def _transport(client: FakeClient, **kwargs) -> SessionTransport:
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
    await _transport(client).search_raw("SC60", QueryType.AUTO)
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


async def test_403_is_hard_stop_not_retried_not_reauth() -> None:
    client = FakeClient([FakeResponse(403), FakeResponse(200)])
    with pytest.raises(AccessForbidden):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 1  # no retry, no reauth loop


async def test_429_is_retried_then_succeeds() -> None:
    client = FakeClient(
        [FakeResponse(429, retry_after="0"), FakeResponse(200, body={"records": []})]
    )
    assert await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO) == []
    assert len(client.requests) == 2


async def test_429_exhausted_raises_live_fetch_error() -> None:
    client = FakeClient([FakeResponse(429), FakeResponse(429), FakeResponse(429)])
    with pytest.raises(LiveFetchError, match="429"):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 3


async def test_retry_after_header_is_capped() -> None:
    captured: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        captured.append(seconds)

    client = FakeClient([FakeResponse(429, retry_after="9999"), FakeResponse(200)])
    transport = SessionTransport(
        client=client,
        base_url="https://portal.alliancels.net",
        allowed_hosts=ALLOWED,
        rate_limiter=RateLimiter(0, sleep=_no_sleep),
        sleep=_record_sleep,
        max_retry_after_seconds=60.0,
    )
    await transport.search_raw("SC60", QueryType.AUTO)
    assert captured == [60.0]  # 9999 capped to the configured max


async def test_transient_5xx_is_retried_then_succeeds() -> None:
    client = FakeClient([FakeResponse(503), FakeResponse(200, body={"records": []})])
    assert await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO) == []
    assert len(client.requests) == 2


async def test_timeout_error_is_retried_then_raises_live_fetch_error() -> None:
    client = FakeClient([TimeoutError(), TimeoutError(), TimeoutError()])
    with pytest.raises(LiveFetchError):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 3


async def test_unrecognised_body_yields_empty_records() -> None:
    client = FakeClient([FakeResponse(200, body={"unexpected": "shape"})])
    assert await _transport(client).search_raw("SC60", QueryType.AUTO) == []


async def test_other_4xx_raises_live_fetch_error() -> None:
    client = FakeClient([FakeResponse(400)])
    with pytest.raises(LiveFetchError):
        await _transport(client).search_raw("SC60", QueryType.AUTO)


async def test_search_response_over_cap_is_rejected() -> None:
    client = FakeClient([FakeResponse(200, content_length=10_000_000)])
    with pytest.raises(ResponseTooLarge):
        await _transport(client, max_response_bytes=1000).search_raw("SC60", QueryType.AUTO)


class TestFetchDocument:
    async def test_download_returns_bytes(self) -> None:
        pdf = b"%PDF-1.4 ...bytes..."
        client = FakeClient([FakeResponse(200, content=pdf)])
        transport = _transport(client)
        url = "https://portal.alliancels.net/s/document/ALS-SC60-SVC"
        assert await transport.fetch_document(url) == pdf

    async def test_download_host_allowlisted(self) -> None:
        client = FakeClient([FakeResponse(200, content=b"x")])
        with pytest.raises(HostNotAllowed):
            await _transport(client).fetch_document("https://cdn.evil.example/x.pdf")
        assert client.requests == []

    async def test_download_over_cap_rejected_by_content_length(self) -> None:
        client = FakeClient([FakeResponse(200, content_length=200_000_000)])
        transport = _transport(client, max_document_bytes=100_000_000)
        with pytest.raises(ResponseTooLarge):
            await transport.fetch_document("https://portal.alliancels.net/s/document/x")

    async def test_download_over_cap_rejected_by_actual_bytes(self) -> None:
        client = FakeClient([FakeResponse(200, content=b"x" * 2000)])
        transport = _transport(client, max_document_bytes=1000)
        with pytest.raises(ResponseTooLarge):
            await transport.fetch_document("https://portal.alliancels.net/s/document/x")


async def test_single_flight_concurrency_is_enforced() -> None:
    """With max_concurrency=1 the client sees at most one in-flight request."""
    in_flight = 0
    max_in_flight = 0

    class ConcurrencyClient:
        requests: list[str] = []

        async def request(self, method: str, url: str):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)  # hold the slot so overlap would show
            in_flight -= 1
            return FakeResponse(200, body={"records": []})

    transport = SessionTransport(
        client=ConcurrencyClient(),
        base_url="https://portal.alliancels.net",
        allowed_hosts=ALLOWED,
        rate_limiter=RateLimiter(0, sleep=_no_sleep),
        sleep=_no_sleep,
        max_concurrency=1,
    )
    await asyncio.gather(
        transport.search_raw("SC60", QueryType.AUTO),
        transport.search_raw("HS-6008", QueryType.AUTO),
    )
    assert max_in_flight == 1
