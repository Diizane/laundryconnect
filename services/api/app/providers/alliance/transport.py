"""Alliance transports: how raw provider records are obtained per mode.

`FixtureTransport` (default) reads sanitised local fixtures and makes no
network request. `SessionTransport` performs authenticated live fetches
using a human-bootstrapped session — but only via the connector's live
gate (access approved, not CI, kill switch off). Its request mechanics
(host allowlist, rate limiting, timeout/retry, session-expiry detection)
are complete and unit-tested against a mocked client; the exact search
endpoint path and response-to-record mapping are confirmed during the
operator-only smoke test against a captured, sanitised fixture, not guessed
here.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from app.providers.alliance.ratelimit import RateLimiter
from app.providers.errors import ProviderError, ReauthenticationRequired
from app.providers.models import QueryType

logger = logging.getLogger(__name__)

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


class FixtureTransport:
    """Serves sanitised fixture records; no network access."""

    def __init__(self, fixtures_dir: Path = _FIXTURES_DIR) -> None:
        self._records = json.loads((fixtures_dir / "search.json").read_text())["records"]

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


class HttpResponse(Protocol):
    status_code: int
    headers: Any

    def json(self) -> Any: ...


class HttpClient(Protocol):
    async def request(self, method: str, url: str) -> HttpResponse: ...


class LiveFetchError(ProviderError):
    """A live fetch failed for a non-auth reason (timeout, server error)."""


class HostNotAllowed(ProviderError):
    """A URL outside the configured host allowlist was attempted."""


_RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
_AUTH_STATUS = frozenset({401, 403})
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})


class SessionTransport:
    """Authenticated live fetch using a bootstrapped session.

    Enforces the safeguards on every request: host allowlist (safeguard 8/
    no off-host follow), conservative rate limiting (7), a request timeout
    and bounded retries on transient failures only, and session-expiry
    detection → `ReauthenticationRequired` (never a silent bypass). The
    caller (connector) has already validated the session and passed the
    live gate.
    """

    def __init__(
        self,
        *,
        client: HttpClient,
        base_url: str,
        allowed_hosts: list[str],
        rate_limiter: RateLimiter,
        max_retries: int = 2,
        search_path: str = "/s/global-search/{query}",
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._allowed_hosts = set(allowed_hosts)
        self._rate_limiter = rate_limiter
        self._max_retries = max_retries
        self._search_path = search_path
        # Injectable backoff sleep (tests pass a no-op).
        import asyncio

        self._sleep = sleep or asyncio.sleep

    def _check_host(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        if host not in self._allowed_hosts:
            # Never disclose the attempted URL beyond its host.
            raise HostNotAllowed(f"host '{host}' is not in the Alliance allowlist")

    async def _request(self, url: str) -> HttpResponse:
        self._check_host(url)
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                response = await self._client.request("GET", url)
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

            status = response.status_code
            if status in _AUTH_STATUS or self._is_login_redirect(response):
                # Session no longer authenticated — a human must re-bootstrap.
                raise ReauthenticationRequired("live session is no longer authenticated")
            if status in _RETRYABLE_STATUS and attempt < self._max_retries:
                await self._sleep(0.5 * (2**attempt))
                continue
            if status >= 400:
                raise LiveFetchError(f"provider returned status {status}")
            return response
        raise LiveFetchError(
            f"request failed ({type(last_exc).__name__ if last_exc else 'unknown'})"
        )

    def _is_login_redirect(self, response: HttpResponse) -> bool:
        if response.status_code not in _REDIRECT_STATUS:
            return False
        location = ""
        try:
            location = str(response.headers.get("location", ""))
        except Exception:
            return False
        return "/login" in location.lower()

    async def search_raw(self, query: str, query_type: QueryType) -> list[dict]:
        """Fetch results for one query. Fetches only this query's results
        (safeguard 8 — no crawling). The response→record mapping is confirmed
        during the operator smoke test; unrecognised shapes yield []."""
        from urllib.parse import quote

        url = f"{self._base_url}{self._search_path.format(query=quote(query.strip()))}"
        response = await self._request(url)
        return self._parse_records(response)

    def _parse_records(self, response: HttpResponse) -> list[dict]:
        """Map a provider response to raw records (same shape FixtureTransport
        yields and the connector normalises). Tolerant: returns [] on an
        unrecognised body. The exact field paths are pinned against a
        captured, sanitised fixture during the smoke test."""
        try:
            body = response.json()
        except Exception:
            logger.warning("alliance live response was not JSON")
            return []
        records = body.get("records") if isinstance(body, dict) else None
        return records if isinstance(records, list) else []
