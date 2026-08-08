"""SessionTransport mechanics — mocked streaming client only, no live requests."""

import asyncio
from collections.abc import AsyncIterator
from email.utils import formatdate

import pytest

from app.providers.alliance.ratelimit import RateLimiter
from app.providers.alliance.transport import (
    AccessForbidden,
    HostNotAllowed,
    InvalidProviderURL,
    LiveFetchError,
    ResponseTooLarge,
    SessionTransport,
    UnexpectedRedirect,
)
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentContent,
    ReauthenticationRequired,
)
from app.providers.models import QueryType

ALLOWED = ["portal.alliancels.net"]


class FakeStreamResponse:
    def __init__(
        self,
        status_code: int,
        *,
        chunks: list[bytes] | None = None,
        location: str = "",
        content_length: int | None = None,
        retry_after: str | None = None,
        content_type: str | None = None,
        etag: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks if chunks is not None else [b'{"records": []}']
        self.chunks_yielded = 0
        self.closed = False
        self.headers: dict[str, str] = {}
        if location:
            self.headers["location"] = location
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        if retry_after is not None:
            self.headers["retry-after"] = retry_after
        if content_type is not None:
            self.headers["content-type"] = content_type
        if etag is not None:
            self.headers["etag"] = etag

    async def aiter_bytes(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.chunks_yielded += 1
            yield chunk


class _StreamCtx:
    def __init__(self, result) -> None:
        self._result = result

    async def __aenter__(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def __aexit__(self, *exc) -> bool:
        if not isinstance(self._result, Exception):
            self._result.closed = True
        return False


class FakeStreamClient:
    def __init__(self, results: list) -> None:
        self._results = list(results)
        self.requests: list[str] = []
        self.request_headers: list[dict[str, str] | None] = []

    def stream(self, method: str, url: str, headers: dict[str, str] | None = None) -> _StreamCtx:
        self.requests.append(url)
        self.request_headers.append(headers)
        return _StreamCtx(self._results.pop(0))


async def _no_sleep(_seconds: float) -> None:
    return None


def _transport(client: FakeStreamClient, **kwargs) -> SessionTransport:
    kwargs.setdefault("search_url_template", "https://portal.alliancels.net/en/Search/{query}")
    return SessionTransport(
        client=client,
        allowed_hosts=ALLOWED,
        rate_limiter=RateLimiter(0, sleep=_no_sleep),
        sleep=_no_sleep,
        **kwargs,
    )


async def test_successful_fetch_returns_records() -> None:
    records = [{"source_reference": "ALS-SC60-SVC", "title": "SC60 Service Manual"}]
    body = b'{"records": [{"source_reference": "ALS-SC60-SVC", "title": "SC60 Service Manual"}]}'
    client = FakeStreamClient([FakeStreamResponse(200, chunks=[body])])
    assert await _transport(client).search_raw("SC60", QueryType.AUTO) == records
    assert len(client.requests) == 1


async def test_only_portal_host_is_fetched() -> None:
    client = FakeStreamClient([FakeStreamResponse(200)])
    await _transport(client).search_raw("SC60", QueryType.AUTO)
    from urllib.parse import urlparse

    assert urlparse(client.requests[0]).hostname == "portal.alliancels.net"


async def test_off_allowlist_host_is_refused() -> None:
    client = FakeStreamClient([FakeStreamResponse(200)])
    transport = SessionTransport(
        client=client,
        search_url_template="https://evil.example.com/{query}",
        allowed_hosts=ALLOWED,
        rate_limiter=RateLimiter(0),
    )
    with pytest.raises(HostNotAllowed):
        await transport.search_raw("SC60", QueryType.AUTO)
    assert client.requests == []


class TestSerialSearchRouting:
    """SERIAL queries use the BySerial endpoint (field-test finding:
    StartsWith prefix-matches model numbers and returns unrelated machines
    for a serial); every other query type keeps the model search."""

    def _transport(self, client: FakeStreamClient) -> SessionTransport:
        return SessionTransport(
            client=client,
            allowed_hosts=["pc.alliancels.net"],
            rate_limiter=RateLimiter(0, sleep=_no_sleep),
            sleep=_no_sleep,
            search_url_template=(
                "https://pc.alliancels.net/en/Search/StartsWith"
                "?searchString={query}&x.Show=Assembly"
            ),
            serial_search_url_template=(
                "https://pc.alliancels.net/en/Search/BySerial?searchString={query}&x.Show=Assembly"
            ),
        )

    async def test_serial_query_uses_by_serial_endpoint(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(200)])
        await self._transport(client).search_raw("1910075972", QueryType.SERIAL)
        assert client.requests[0].startswith(
            "https://pc.alliancels.net/en/Search/BySerial?searchString=1910075972"
        )

    @pytest.mark.parametrize(
        "query_type",
        [QueryType.AUTO, QueryType.MODEL, QueryType.PART, QueryType.KEYWORD],
    )
    async def test_other_query_types_keep_model_search(self, query_type: QueryType) -> None:
        client = FakeStreamClient([FakeStreamResponse(200)])
        await self._transport(client).search_raw("DR75", query_type)
        assert "/en/Search/StartsWith" in client.requests[0]

    async def test_serial_without_template_falls_back_to_model_search(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(200)])
        transport = SessionTransport(
            client=client,
            allowed_hosts=["pc.alliancels.net"],
            rate_limiter=RateLimiter(0, sleep=_no_sleep),
            sleep=_no_sleep,
            search_url_template="https://pc.alliancels.net/en/Search/StartsWith?q={query}",
        )
        await transport.search_raw("1910075972", QueryType.SERIAL)
        assert "/en/Search/StartsWith" in client.requests[0]

    async def test_serial_query_is_url_encoded(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(200)])
        await self._transport(client).search_raw("135RX 009281/WK", QueryType.SERIAL)
        assert "searchString=135RX%20009281%2FWK" in client.requests[0]


async def test_conditional_headers_are_passed_as_a_keyword() -> None:
    """httpx's `stream()` takes headers keyword-only; its third positional
    slot is `content`. Passing positionally raised TypeError against real
    httpx while fakes accepted it — caught only in deployment. The fakes are
    now keyword-only too, so this test fails if the call regresses."""
    client = FakeStreamClient(
        [FakeStreamResponse(200, chunks=[b"%PDF-1.4 x"], content_type="application/pdf")]
    )
    conditional = {"If-None-Match": '"v1"'}
    await _transport(client).fetch_document(
        "https://portal.alliancels.net/manuals/Production/D0568.pdf",
        conditional=conditional,
    )
    assert client.request_headers == [conditional]


async def test_304_raises_not_modified_without_reading_a_body() -> None:
    from app.providers.alliance.transport import NotModified

    response = FakeStreamResponse(304, chunks=[b"should not be read"])
    client = FakeStreamClient([response])
    with pytest.raises(NotModified):
        await _transport(client).fetch_document(
            "https://portal.alliancels.net/manuals/Production/D0568.pdf",
            conditional={"If-None-Match": '"v1"'},
        )
    assert response.chunks_yielded == 0  # no transfer: that is the point
    assert len(client.requests) == 1  # terminal, never retried


async def test_document_validators_are_captured_for_the_cache() -> None:
    client = FakeStreamClient(
        [
            FakeStreamResponse(
                200, chunks=[b"%PDF-1.4 x"], content_type="application/pdf", etag='"abc123"'
            )
        ]
    )
    transport = _transport(client)
    await transport.fetch_document("https://portal.alliancels.net/manuals/P/D.pdf")
    assert transport.last_document_validators["etag"] == '"abc123"'


async def test_parts_connection_host_allowed_and_query_encoded() -> None:
    client = FakeStreamClient([FakeStreamResponse(200)])
    transport = SessionTransport(
        client=client,
        search_url_template=(
            "https://pc.alliancels.net/en/Search/StartsWith?searchString={query}&x.Show=Assembly"
        ),
        allowed_hosts=["portal.alliancels.net", "pc.alliancels.net"],
        rate_limiter=RateLimiter(0, sleep=_no_sleep),
        sleep=_no_sleep,
    )
    await transport.search_raw("SC 60/A", QueryType.AUTO)
    from urllib.parse import urlparse

    fetched = client.requests[0]
    assert urlparse(fetched).hostname == "pc.alliancels.net"
    assert "searchString=SC%2060%2FA" in fetched  # query URL-encoded
    assert "x.Show=Assembly" in fetched


async def test_401_raises_reauthentication_required() -> None:
    client = FakeStreamClient([FakeStreamResponse(401)])
    with pytest.raises(ReauthenticationRequired):
        await _transport(client).search_raw("SC60", QueryType.AUTO)


async def test_login_redirect_raises_reauthentication_required() -> None:
    response = FakeStreamResponse(302, location="https://portal.alliancels.net/s/login/")
    client = FakeStreamClient([response])
    with pytest.raises(ReauthenticationRequired):
        await _transport(client).search_raw("SC60", QueryType.AUTO)
    assert response.chunks_yielded == 0  # redirect body never read
    assert len(client.requests) == 1


class TestUrlPolicy:
    """Every live URL must be https, exact-host, no userinfo, port 443 only —
    rejected before any stream is opened."""

    def _tmpl(self, template: str, client: FakeStreamClient) -> SessionTransport:
        return SessionTransport(
            client=client,
            search_url_template=template,
            allowed_hosts=ALLOWED,
            rate_limiter=RateLimiter(0, sleep=_no_sleep),
            sleep=_no_sleep,
        )

    async def test_http_scheme_rejected(self) -> None:
        client = FakeStreamClient([])
        with pytest.raises(InvalidProviderURL):
            await self._tmpl("http://portal.alliancels.net/s/{query}", client).search_raw(
                "SC60", QueryType.AUTO
            )
        assert client.requests == []  # stream never opened

    async def test_userinfo_rejected(self) -> None:
        client = FakeStreamClient([])
        with pytest.raises(InvalidProviderURL):
            await self._tmpl(
                "https://user:password@portal.alliancels.net/s/{query}", client
            ).search_raw("SC60", QueryType.AUTO)
        assert client.requests == []

    async def test_non_443_port_rejected(self) -> None:
        client = FakeStreamClient([])
        with pytest.raises(InvalidProviderURL):
            await self._tmpl("https://portal.alliancels.net:444/s/{query}", client).search_raw(
                "SC60", QueryType.AUTO
            )
        assert client.requests == []

    async def test_off_allowlist_host_rejected(self) -> None:
        client = FakeStreamClient([])
        with pytest.raises(HostNotAllowed):
            await self._tmpl("https://evil.example/{query}", client).search_raw(
                "SC60", QueryType.AUTO
            )
        assert client.requests == []

    async def test_plain_https_portal_accepted(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(200)])
        assert (
            await self._tmpl("https://portal.alliancels.net/s/{query}", client).search_raw(
                "SC60", QueryType.AUTO
            )
            == []
        )
        assert len(client.requests) == 1

    async def test_explicit_port_443_accepted(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(200)])
        await self._tmpl("https://portal.alliancels.net:443/s/{query}", client).search_raw(
            "SC60", QueryType.AUTO
        )
        assert len(client.requests) == 1


class TestUnexpectedRedirects:
    async def test_same_host_non_login_redirect_is_terminal(self) -> None:
        response = FakeStreamResponse(302, location="https://portal.alliancels.net/s/elsewhere")
        client = FakeStreamClient([response, FakeStreamResponse(200)])
        with pytest.raises(UnexpectedRedirect):
            await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
        assert response.chunks_yielded == 0  # body not consumed
        assert len(client.requests) == 1  # not retried, no second request

    async def test_off_host_redirect_is_refused_terminally(self) -> None:
        response = FakeStreamResponse(302, location="https://evil.example/x?token=SECRETVALUE")
        client = FakeStreamClient([response, FakeStreamResponse(200)])
        with pytest.raises(UnexpectedRedirect) as excinfo:
            await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
        message = str(excinfo.value)
        assert "off-host" in message
        assert "evil.example" in message
        assert "SECRETVALUE" not in message  # no query params leaked
        assert response.chunks_yielded == 0
        assert len(client.requests) == 1


async def test_403_is_hard_stop_not_retried_not_reauth() -> None:
    client = FakeStreamClient([FakeStreamResponse(403), FakeStreamResponse(200)])
    with pytest.raises(AccessForbidden):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 1


async def test_429_is_retried_then_succeeds() -> None:
    client = FakeStreamClient([FakeStreamResponse(429, retry_after="0"), FakeStreamResponse(200)])
    assert await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO) == []
    assert len(client.requests) == 2  # fresh stream per attempt, no reuse


async def test_429_exhausted_raises_live_fetch_error() -> None:
    client = FakeStreamClient(
        [FakeStreamResponse(429), FakeStreamResponse(429), FakeStreamResponse(429)]
    )
    with pytest.raises(LiveFetchError, match="429"):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 3


async def test_transient_5xx_is_retried_then_succeeds() -> None:
    client = FakeStreamClient([FakeStreamResponse(503), FakeStreamResponse(200)])
    assert await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO) == []
    assert len(client.requests) == 2


async def test_timeout_error_is_retried_then_raises_live_fetch_error() -> None:
    client = FakeStreamClient([TimeoutError(), TimeoutError(), TimeoutError()])
    with pytest.raises(LiveFetchError):
        await _transport(client, max_retries=2).search_raw("SC60", QueryType.AUTO)
    assert len(client.requests) == 3


async def test_other_4xx_raises_live_fetch_error() -> None:
    client = FakeStreamClient([FakeStreamResponse(400)])
    with pytest.raises(LiveFetchError):
        await _transport(client).search_raw("SC60", QueryType.AUTO)


async def test_unrecognised_body_yields_empty_records() -> None:
    client = FakeStreamClient([FakeStreamResponse(200, chunks=[b'{"unexpected": 1}'])])
    assert await _transport(client).search_raw("SC60", QueryType.AUTO) == []


class TestStreamingSizeCaps:
    async def test_content_length_precheck_stops_before_reading(self) -> None:
        # Declared 10 MB, cap 1000 → reject WITHOUT reading any chunk.
        response = FakeStreamResponse(200, content_length=10_000_000, chunks=[b"x" * 100])
        client = FakeStreamClient([response])
        with pytest.raises(ResponseTooLarge):
            await _transport(client, max_response_bytes=1000).search_raw("SC60", QueryType.AUTO)
        assert response.chunks_yielded == 0  # never started reading the body
        assert response.closed is True

    async def test_streaming_stops_once_limit_exceeded_no_content_length(self) -> None:
        # No Content-Length; 10×1 MB chunks, cap 5 MB → stop mid-stream.
        chunks = [b"x" * 1_000_000 for _ in range(10)]
        response = FakeStreamResponse(200, chunks=chunks)
        client = FakeStreamClient([response])
        with pytest.raises(ResponseTooLarge):
            await _transport(client, max_response_bytes=5_000_000).search_raw(
                "SC60", QueryType.AUTO
            )
        # Read stopped early — did NOT consume all 10 chunks — and closed.
        assert 0 < response.chunks_yielded < 10
        assert response.closed is True

    async def test_document_streaming_cap_enforced(self) -> None:
        # A genuine PDF stream (correct type and magic) that exceeds the cap
        # must still be aborted mid-stream.
        chunks = [b"%PDF-1.4" + b"x" * 1_000_000] + [b"x" * 1_000_000 for _ in range(9)]
        response = FakeStreamResponse(200, chunks=chunks, content_type="application/pdf")
        client = FakeStreamClient([response])
        transport = _transport(client, max_document_bytes=3_000_000)
        with pytest.raises(ResponseTooLarge):
            await transport.fetch_document("https://portal.alliancels.net/s/document/x")
        assert 0 < response.chunks_yielded < 10


class TestFetchDocument:
    async def test_download_returns_validated_pdf_bytes(self) -> None:
        pdf = b"%PDF-1.4 ...bytes..."
        client = FakeStreamClient(
            [FakeStreamResponse(200, chunks=[pdf], content_type="application/pdf")]
        )
        url = "https://portal.alliancels.net/s/document/ALS-SC60-SVC"
        assert await _transport(client).fetch_document(url) == pdf

    async def test_content_type_with_charset_parameter_accepted(self) -> None:
        pdf = b"%PDF-1.7 body"
        client = FakeStreamClient(
            [FakeStreamResponse(200, chunks=[pdf], content_type="application/pdf; charset=utf-8")]
        )
        url = "https://portal.alliancels.net/s/document/x"
        assert await _transport(client).fetch_document(url) == pdf

    async def test_download_host_allowlisted(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(200, chunks=[b"x"])])
        with pytest.raises(HostNotAllowed):
            await _transport(client).fetch_document("https://cdn.evil.example/x.pdf")
        assert client.requests == []

    async def test_html_where_pdf_expected_rejected_before_body_read(self) -> None:
        # An HTML page at the final fetch stage (wrong/expired/error page) is
        # a terminal InvalidDocumentContent — and the body is NEVER read.
        response = FakeStreamResponse(
            200, chunks=[b"<html>login page</html>"], content_type="text/html; charset=utf-8"
        )
        client = FakeStreamClient([response, FakeStreamResponse(200)])
        with pytest.raises(InvalidDocumentContent):
            await _transport(client, max_retries=2).fetch_document(
                "https://portal.alliancels.net/manuals/Production/D0100.pdf"
            )
        assert response.chunks_yielded == 0  # rejected on headers alone
        assert len(client.requests) == 1  # terminal — never retried

    async def test_missing_content_type_rejected(self) -> None:
        response = FakeStreamResponse(200, chunks=[b"%PDF-1.4"])
        client = FakeStreamClient([response])
        with pytest.raises(InvalidDocumentContent):
            await _transport(client).fetch_document("https://portal.alliancels.net/manuals/x.pdf")
        assert response.chunks_yielded == 0

    async def test_pdf_content_type_but_non_pdf_body_aborts_early(self) -> None:
        # Misconfigured server: declares PDF, serves HTML. The magic-byte
        # check aborts on the FIRST chunk instead of streaming to the cap.
        chunks = [b"<html>not a pdf</html>"] + [b"x" * 1000 for _ in range(50)]
        response = FakeStreamResponse(200, chunks=chunks, content_type="application/pdf")
        client = FakeStreamClient([response])
        with pytest.raises(InvalidDocumentContent):
            await _transport(client).fetch_document("https://portal.alliancels.net/manuals/x.pdf")
        assert response.chunks_yielded == 1  # aborted immediately
        assert response.closed is True

    async def test_body_shorter_than_magic_rejected(self) -> None:
        response = FakeStreamResponse(200, chunks=[b"%P"], content_type="application/pdf")
        client = FakeStreamClient([response])
        with pytest.raises(InvalidDocumentContent):
            await _transport(client).fetch_document("https://portal.alliancels.net/manuals/x.pdf")

    async def test_404_maps_to_document_not_found_terminally(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(404), FakeStreamResponse(200)])
        with pytest.raises(DocumentNotFound):
            await _transport(client, max_retries=2).fetch_document(
                "https://portal.alliancels.net/manuals/Production/D9999.pdf"
            )
        assert len(client.requests) == 1  # never retried

    async def test_401_still_raises_reauthentication_required(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(401)])
        with pytest.raises(ReauthenticationRequired):
            await _transport(client).fetch_document("https://portal.alliancels.net/manuals/x.pdf")

    async def test_login_redirect_still_raises_reauthentication_required(self) -> None:
        # Phase 1 observed: unauthenticated document requests 302 to login.
        response = FakeStreamResponse(
            302, location="https://portal.alliancels.net/?ReturnUrl=%2fmanuals%2fx.pdf&login=1"
        )
        client = FakeStreamClient([response])
        with pytest.raises(ReauthenticationRequired):
            await _transport(client).fetch_document("https://portal.alliancels.net/manuals/x.pdf")

    async def test_off_host_redirect_refused(self) -> None:
        response = FakeStreamResponse(302, location="https://cdn.evil.example/x.pdf?sig=SECRET")
        client = FakeStreamClient([response])
        with pytest.raises(UnexpectedRedirect) as excinfo:
            await _transport(client).fetch_document("https://portal.alliancels.net/manuals/x.pdf")
        assert "SECRET" not in str(excinfo.value)

    async def test_403_is_hard_stop(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(403), FakeStreamResponse(200)])
        with pytest.raises(AccessForbidden):
            await _transport(client, max_retries=2).fetch_document(
                "https://portal.alliancels.net/manuals/x.pdf"
            )
        assert len(client.requests) == 1


class TestFetchPage:
    async def test_returns_html_bytes_without_content_validation(self) -> None:
        html = b"<html><body>manual menu</body></html>"
        client = FakeStreamClient([FakeStreamResponse(200, chunks=[html])])
        url = "https://portal.alliancels.net/en/Manual?ManualId=1"
        assert await _transport(client).fetch_page(url) == html

    async def test_404_maps_to_document_not_found(self) -> None:
        client = FakeStreamClient([FakeStreamResponse(404)])
        with pytest.raises(DocumentNotFound):
            await _transport(client).fetch_page("https://portal.alliancels.net/en/Manual?x=1")

    async def test_search_404_is_still_a_generic_fetch_error(self) -> None:
        # The 404 → DocumentNotFound mapping is document-workflow-only; the
        # search path's contract is unchanged.
        client = FakeStreamClient([FakeStreamResponse(404)])
        with pytest.raises(LiveFetchError):
            await _transport(client).search_raw("SC60", QueryType.AUTO)

    async def test_page_size_cap_is_search_cap(self) -> None:
        chunks = [b"x" * 1_000_000 for _ in range(10)]
        response = FakeStreamResponse(200, chunks=chunks)
        client = FakeStreamClient([response])
        with pytest.raises(ResponseTooLarge):
            await _transport(client, max_response_bytes=2_000_000).fetch_page(
                "https://portal.alliancels.net/en/Manual?x=1"
            )
        assert 0 < response.chunks_yielded < 10

    async def test_off_allowlist_page_refused(self) -> None:
        client = FakeStreamClient([])
        with pytest.raises(HostNotAllowed):
            await _transport(client).fetch_page("https://evil.example/en/Manual")
        assert client.requests == []


class TestRetryAfterParsing:
    def _t(self, **kwargs) -> SessionTransport:
        return _transport(FakeStreamClient([]), **kwargs)

    def test_numeric_seconds_within_range(self) -> None:
        transport = self._t(max_retry_after_seconds=60)
        assert transport._retry_after_seconds(FakeStreamResponse(429, retry_after="5"), 0) == 5.0

    def test_negative_clamped_to_zero(self) -> None:
        transport = self._t(max_retry_after_seconds=60)
        assert transport._retry_after_seconds(FakeStreamResponse(429, retry_after="-5"), 0) == 0.0

    def test_oversized_clamped_to_max(self) -> None:
        transport = self._t(max_retry_after_seconds=60)
        assert (
            transport._retry_after_seconds(FakeStreamResponse(429, retry_after="9999"), 0) == 60.0
        )

    def test_invalid_falls_back_to_exponential_backoff(self) -> None:
        transport = self._t()
        # attempt 1 → 0.5 * 2**1 = 1.0
        assert transport._retry_after_seconds(FakeStreamResponse(429, retry_after="soon"), 1) == 1.0

    def test_http_date_form_supported(self) -> None:
        fixed_now = 1_000_000.0
        transport = SessionTransport(
            client=FakeStreamClient([]),
            search_url_template="https://portal.alliancels.net/s/{query}",
            allowed_hosts=ALLOWED,
            rate_limiter=RateLimiter(0, sleep=_no_sleep),
            sleep=_no_sleep,
            now=lambda: fixed_now,
            max_retry_after_seconds=60,
        )
        http_date = formatdate(fixed_now + 30, usegmt=True)  # 30s in the future
        delay = transport._retry_after_seconds(FakeStreamResponse(429, retry_after=http_date), 0)
        assert abs(delay - 30.0) < 2.0

    def test_http_date_in_past_clamped_to_zero(self) -> None:
        fixed_now = 1_000_000.0
        transport = SessionTransport(
            client=FakeStreamClient([]),
            search_url_template="https://portal.alliancels.net/s/{query}",
            allowed_hosts=ALLOWED,
            rate_limiter=RateLimiter(0, sleep=_no_sleep),
            sleep=_no_sleep,
            now=lambda: fixed_now,
        )
        http_date = formatdate(fixed_now - 100, usegmt=True)
        assert (
            transport._retry_after_seconds(FakeStreamResponse(429, retry_after=http_date), 0) == 0.0
        )


async def test_single_flight_concurrency_is_enforced() -> None:
    in_flight = 0
    max_in_flight = 0

    class ConcurrencyResponse(FakeStreamResponse):
        async def aiter_bytes(self, chunk_size: int = 65536):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)  # hold the slot so overlap would show
            in_flight -= 1
            yield b'{"records": []}'

    class ConcurrencyClient:
        requests: list[str] = []

        def stream(
            self, method: str, url: str, *, headers: dict[str, str] | None = None
        ) -> _StreamCtx:
            return _StreamCtx(ConcurrencyResponse(200))

    transport = SessionTransport(
        client=ConcurrencyClient(),
        search_url_template="https://portal.alliancels.net/s/{query}",
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
