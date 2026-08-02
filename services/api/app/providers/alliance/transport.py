"""Alliance transports: how raw provider records are obtained per mode.

`FixtureTransport` (default) reads sanitised local fixtures and makes no
network request. `SessionTransport` performs authenticated live fetches
using a human-bootstrapped session — but only via the connector's live
gate (access approved, not CI, kill switch off). Its request mechanics
(host allowlist, URL policy, rate limiting, streaming size caps, timeout/
retry, redirect/session handling) are unit-tested against a mocked client.
Body parsing is pluggable (`parser`); production injects the Parts
Connection HTML parser, pinned against a captured, sanitised SC60 response.
"""

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from app.providers.alliance.ratelimit import RateLimiter
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentContent,
    ProviderError,
    ProviderForbidden,
    ReauthenticationRequired,
)
from app.providers.models import QueryType

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65536

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Which fields a query matches against, per query type (AUTO/KEYWORD: all).
_FIELDS_BY_QUERY_TYPE: dict[QueryType, tuple[str, ...]] = {
    QueryType.MODEL: ("model",),
    QueryType.SERIAL: ("serial_range",),
    QueryType.PART: ("part_number",),
    QueryType.FAULT_CODE: ("title", "description"),
}


class AllianceTransport(Protocol):
    async def search_raw(self, query: str, query_type: QueryType) -> list[dict]: ...

    # Document workflow (Milestone 9): one bounded intermediate page fetch,
    # one validated document fetch. Implementations never crawl.
    async def fetch_page(self, url: str) -> bytes: ...

    async def fetch_document(self, url: str) -> bytes: ...


class FixtureTransport:
    """Serves sanitised fixture records and pages; no network access.

    The document workflow serves reconstructed, sanitised HTML fixtures so
    fixture mode exercises the REAL page parsers end-to-end, mirroring the
    live traversal without any network request.
    """

    def __init__(self, fixtures_dir: Path = _FIXTURES_DIR) -> None:
        self._fixtures_dir = fixtures_dir
        self._records = json.loads((fixtures_dir / "search.json").read_text())["records"]

    async def fetch_page(self, url: str) -> bytes:
        path = urlparse(url).path
        if path.startswith("/en/Model/Literature"):
            return (self._fixtures_dir / "literature_page.html").read_bytes()
        if path.startswith("/en/Manual"):
            return (self._fixtures_dir / "manual_page.html").read_bytes()
        raise DocumentNotFound("no fixture page for this path")

    async def fetch_document(self, url: str) -> bytes:
        path = urlparse(url).path
        if not (path.startswith("/manuals/") and path.endswith(".pdf")):
            raise DocumentNotFound("no fixture document at this path")
        body = (self._fixtures_dir / "document.pdf").read_bytes()
        if not body.startswith(b"%PDF-"):  # same guarantee as the live path
            raise InvalidDocumentContent("fixture document is not a PDF")
        return body

    async def search_raw(self, query: str, query_type: QueryType) -> list[dict]:
        needle = query.strip().lower()
        if not needle:
            return []
        fields = _FIELDS_BY_QUERY_TYPE.get(query_type)
        matches = []
        for record in self._records:
            haystacks = (
                [record.get(field) for field in fields]
                if fields
                else [
                    record.get("title"),
                    record.get("description"),
                    record.get("model"),
                    record.get("part_number"),
                    record.get("brand"),
                    record.get("manufacturer"),
                ]
            )
            if any(needle in str(value).lower() for value in haystacks if value):
                matches.append(record)
        return matches


class StreamResponse(Protocol):
    status_code: int
    headers: Any

    def aiter_bytes(self, chunk_size: int = _CHUNK_SIZE) -> AsyncIterator[bytes]: ...


class StreamingClient(Protocol):
    def stream(self, method: str, url: str) -> AbstractAsyncContextManager[StreamResponse]: ...


class LiveFetchError(ProviderError):
    """A live fetch failed for a non-auth reason (timeout, server error)."""


class HostNotAllowed(ProviderError):
    """A URL whose host is outside the configured allowlist was attempted."""


class InvalidProviderURL(ProviderError):
    """A URL violated the scheme/userinfo/port policy for live requests."""


class UnexpectedRedirect(ProviderError):
    """A non-login 3xx redirect was refused (never followed)."""


class ResponseTooLarge(LiveFetchError):
    """A response exceeded the configured size cap."""


class AccessForbidden(ProviderForbidden):
    """The provider returned 403 — stop and review; may indicate blocking.
    A `ProviderForbidden` so the registry surfaces a distinct `forbidden`
    outcome (not a generic failure)."""


# Raised/re-raised terminally; never caught by the transient-retry handler.
_TERMINAL = (
    ReauthenticationRequired,
    AccessForbidden,
    ResponseTooLarge,
    HostNotAllowed,
    InvalidProviderURL,
    UnexpectedRedirect,
    DocumentNotFound,
    InvalidDocumentContent,
    LiveFetchError,
)
_RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})


class SessionTransport:
    """Authenticated live fetch using a bootstrapped session.

    Genuinely streaming: response bodies are read incrementally and the
    download is aborted the instant accumulated bytes exceed the applicable
    cap (search 5 MB, document 100 MB), with a Content-Length pre-check when
    present. Per-request safeguards preserved: host allowlist (redirects
    never followed — client built with follow_redirects=False), single-
    flight concurrency, conservative rate limiting, bounded retries on
    transient failures only, and explicit 401/403/429/5xx handling. 401 or a
    login redirect → `ReauthenticationRequired`; 403 → hard stop (possible
    block, not retried, not reauth-looped). The caller has already validated
    the session and passed the live gate.
    """

    def __init__(
        self,
        *,
        client: StreamingClient,
        allowed_hosts: list[str],
        rate_limiter: RateLimiter,
        max_retries: int = 2,
        max_concurrency: int = 1,
        max_retry_after_seconds: float = 60.0,
        max_response_bytes: int = 5 * 1024 * 1024,
        max_document_bytes: int = 100 * 1024 * 1024,
        search_url_template: str = (
            "https://pc.alliancels.net/en/Search/StartsWith?searchString={query}&x.Show=Assembly"
        ),
        serial_search_url_template: str | None = None,
        parser: Callable[[bytes], list[dict]] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        import asyncio

        self._client = client
        self._parser = parser or parse_json_records
        self._allowed_hosts = set(allowed_hosts)
        self._rate_limiter = rate_limiter
        self._max_retries = max_retries
        self._max_retry_after = max_retry_after_seconds
        self._max_response_bytes = max_response_bytes
        self._max_document_bytes = max_document_bytes
        self._search_url_template = search_url_template
        # SERIAL queries use the portal's dedicated BySerial endpoint (exact
        # machine resolution); when unset, all queries use the model search.
        self._serial_search_url_template = serial_search_url_template
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._sleep = sleep or asyncio.sleep
        self._now = now

    def _check_url(self, url: str) -> None:
        """Enforce the live-URL policy before opening a stream: https only,
        exact allowlisted host, no userinfo, and no explicit port other than
        443. Error messages never include the full URL."""
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise InvalidProviderURL("live URL scheme must be https")
        if parsed.username or parsed.password:
            raise InvalidProviderURL("live URL must not contain userinfo")
        host = parsed.hostname or ""
        if host not in self._allowed_hosts:
            # Never disclose the attempted URL beyond its host.
            raise HostNotAllowed(f"host '{host}' is not in the Alliance allowlist")
        try:
            port = parsed.port
        except ValueError:
            raise InvalidProviderURL("live URL has an invalid port") from None
        if port is not None and port != 443:
            raise InvalidProviderURL("live URL explicit port must be 443")

    def _sanitise_location(self, response: StreamResponse) -> tuple[str, str]:
        """Return (host, path) of a Location header — never query/fragment/
        userinfo, so redirect diagnostics leak nothing sensitive."""
        try:
            location = str(response.headers.get("location", ""))
        except Exception:
            return ("", "")
        parts = urlparse(location)
        return (parts.hostname or "", parts.path or "")

    def _retry_after_seconds(self, response: StreamResponse, attempt: int) -> float:
        """Retry-After → delay, clamped to [0, max]. Supports numeric seconds
        and the HTTP-date form; invalid values fall back to exponential
        backoff."""
        default = 0.5 * (2**attempt)
        try:
            raw = response.headers.get("retry-after")
        except Exception:
            return default
        if raw is None:
            return default
        raw = str(raw).strip()
        try:  # numeric seconds
            return max(0.0, min(float(raw), self._max_retry_after))
        except (TypeError, ValueError):
            pass
        try:  # HTTP-date
            parsed = parsedate_to_datetime(raw)
            if parsed is not None:
                delta = parsed.timestamp() - self._now()
                return max(0.0, min(delta, self._max_retry_after))
        except (TypeError, ValueError, OverflowError):
            pass
        return default

    def _is_login_redirect(self, response: StreamResponse) -> bool:
        """A redirect that means "session expired, go log in". Two observed
        forms: a /login path, and (Phase 1, document workflow) a redirect to
        the site root carrying a ReturnUrl parameter
        (`Location: /?ReturnUrl=<original path>`)."""
        if response.status_code not in _REDIRECT_STATUS:
            return False
        try:
            location = str(response.headers.get("location", "")).lower()
        except Exception:
            return False
        return "/login" in location or "returnurl=" in location

    def _check_content_type(self, response: StreamResponse, expected: str) -> None:
        """Require the declared Content-Type (media type only; parameters
        such as charset ignored). The error message carries the declared
        media type — a structural header value, never response content."""
        try:
            raw = str(response.headers.get("content-type", "") or "")
        except Exception:
            raw = ""
        media_type = raw.split(";", 1)[0].strip().lower()
        if media_type != expected:
            raise InvalidDocumentContent(
                f"expected content type '{expected}', got '{media_type or 'unknown'}'"
            )

    def _check_declared_size(self, response: StreamResponse, max_bytes: int) -> None:
        try:
            declared = response.headers.get("content-length")
        except Exception:
            declared = None
        if declared is None:
            return
        try:
            if int(declared) > max_bytes:
                raise ResponseTooLarge(f"declared size exceeds {max_bytes} bytes")
        except (TypeError, ValueError):
            pass  # malformed header — fall back to the streaming cap

    async def _read_capped(
        self, response: StreamResponse, max_bytes: int, magic: bytes | None = None
    ) -> bytes:
        """Accumulate the body incrementally; abort the instant the cap is
        exceeded (raising exits the `async with`, closing the stream). When
        `magic` is given, the leading bytes are checked as soon as enough
        have arrived — a mislabelled non-document aborts the download early
        instead of streaming to the cap."""
        buffer = bytearray()
        magic_checked = magic is None
        async for chunk in response.aiter_bytes(_CHUNK_SIZE):
            buffer += chunk
            if not magic_checked and len(buffer) >= len(magic):
                if not bytes(buffer[: len(magic)]) == magic:
                    raise InvalidDocumentContent("document body does not match expected format")
                magic_checked = True
            if len(buffer) > max_bytes:
                raise ResponseTooLarge(f"streamed body exceeded {max_bytes} bytes")
        if not magic_checked:  # body ended before enough bytes for the check
            raise InvalidDocumentContent("document body does not match expected format")
        return bytes(buffer)

    async def _fetch(
        self,
        url: str,
        max_bytes: int,
        *,
        map_404: bool = False,
        require_pdf: bool = False,
    ) -> bytes:
        """Fetch a URL as bounded bytes, streaming. Each attempt opens a
        fresh stream — a consumed/aborted response is never reused.

        Document-workflow options: `map_404` turns HTTP 404 into the domain
        `DocumentNotFound` (terminal); `require_pdf` enforces
        `Content-Type: application/pdf` before the body is read AND a
        `%PDF-` magic-byte check on the leading bytes (terminal
        `InvalidDocumentContent` on either failure)."""
        self._check_url(url)
        async with self._semaphore:  # single-flight concurrency cap
            last_exc: Exception | None = None
            for attempt in range(self._max_retries + 1):
                await self._rate_limiter.acquire()
                try:
                    async with self._client.stream("GET", url) as response:
                        status = response.status_code
                        if status == 401:
                            raise ReauthenticationRequired(
                                "live session is no longer authenticated"
                            )
                        if status in _REDIRECT_STATUS:
                            # Never follow, read, or retry a redirect. Login
                            # redirects mean the session expired; any other
                            # 3xx is a terminal refusal (off-host or not).
                            if self._is_login_redirect(response):
                                raise ReauthenticationRequired(
                                    "live session is no longer authenticated"
                                )
                            dest_host, dest_path = self._sanitise_location(response)
                            if dest_host and dest_host not in self._allowed_hosts:
                                raise UnexpectedRedirect(
                                    f"refused off-host redirect to {dest_host}{dest_path}"
                                )
                            raise UnexpectedRedirect(
                                f"refused unexpected redirect to {dest_host}{dest_path}"
                            )
                        if status == 403:
                            raise AccessForbidden(
                                "provider returned 403 (forbidden) — stopping for review"
                            )
                        if status == 429:
                            if attempt < self._max_retries:
                                await self._sleep(self._retry_after_seconds(response, attempt))
                                continue
                            raise LiveFetchError("provider rate-limited (429) after retries")
                        if status == 404 and map_404:
                            raise DocumentNotFound("provider has no document at this location")
                        if status in _RETRYABLE_STATUS and attempt < self._max_retries:
                            await self._sleep(0.5 * (2**attempt))
                            continue
                        if status >= 400:
                            raise LiveFetchError(f"provider returned status {status}")
                        # 2xx: validate the declared type before reading any
                        # body bytes, then enforce the cap before and during
                        # the read (with the magic-byte check on the leading
                        # bytes when a PDF is required).
                        if require_pdf:
                            self._check_content_type(response, "application/pdf")
                        self._check_declared_size(response, max_bytes)
                        return await self._read_capped(
                            response, max_bytes, magic=b"%PDF-" if require_pdf else None
                        )
                except _TERMINAL:
                    raise  # never retried
                except Exception as exc:  # transport-level (timeout, connection)
                    last_exc = exc
                    logger.warning(
                        "alliance live request errored",
                        extra={"attempt": attempt, "error": type(exc).__name__},
                    )
                    if attempt < self._max_retries:
                        await self._sleep(0.5 * (2**attempt))
                        continue
                    raise LiveFetchError(f"request failed ({type(exc).__name__})") from exc
        raise LiveFetchError(
            f"request failed ({type(last_exc).__name__ if last_exc else 'unknown'})"
        )

    def _search_url(self, query: str, query_type: QueryType = QueryType.AUTO) -> str:
        from urllib.parse import quote

        template = self._search_url_template
        if query_type is QueryType.SERIAL and self._serial_search_url_template:
            # The model StartsWith search prefix-matches model numbers and
            # returns unrelated machines for a serial (field-test finding);
            # BySerial resolves the exact factory configuration instead.
            template = self._serial_search_url_template
        return template.format(query=quote(query.strip(), safe=""))

    async def search_raw(self, query: str, query_type: QueryType) -> list[dict]:
        """Fetch results for one query (safeguard 8 — no crawling). Body is
        streamed under the 5 MB cap, then handed to the configured parser
        (Alliance Parts Connection HTML in production). SERIAL queries use
        the dedicated BySerial endpoint; the response shares the same
        results-table shape, so the parser is unchanged."""
        body = await self._fetch(self._search_url(query, query_type), self._max_response_bytes)
        return self._parser(body)

    async def fetch_search_raw(self, query: str) -> bytes:
        """Return the raw (bounded) search response bytes — used only by the
        operator smoke test to capture the real response for parser pinning.
        Applies every safeguard; never parses."""
        return await self._fetch(self._search_url(query), self._max_response_bytes)

    async def fetch_page(self, url: str) -> bytes:
        """Fetch ONE intermediate HTML page of the bounded document workflow
        (`/en/Manual` menu or `/en/Model/Literature` list), under the search
        size cap. Every transport safeguard applies; 404 maps to
        `DocumentNotFound`. Callers never follow links beyond the observed
        two-page traversal (Milestone 9 Phase 1 findings)."""
        return await self._fetch(url, self._max_response_bytes, map_404=True)

    async def fetch_document(self, url: str) -> bytes:
        """Download a single validated PDF, streamed under the 100 MB cap.
        Host-allowlisted; `Content-Type: application/pdf` enforced before the
        body is read; leading bytes must be `%PDF-` (early abort otherwise);
        404 maps to `DocumentNotFound`. No unbounded transfer into memory;
        no crawling."""
        return await self._fetch(url, self._max_document_bytes, map_404=True, require_pdf=True)


def parse_json_records(body: bytes) -> list[dict]:
    """Default parser: a JSON `{"records": [...]}` body. Tolerant: [] on an
    unrecognised body. Production uses the Parts Connection HTML parser
    instead (injected by the connector)."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        logger.warning("alliance response was not JSON")
        return []
    records = data.get("records") if isinstance(data, dict) else None
    return records if isinstance(records, list) else []
