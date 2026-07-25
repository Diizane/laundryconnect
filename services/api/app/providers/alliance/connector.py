"""Alliance Laundry Systems connector.

Fixture mode by default (no network, CI-safe). Session mode validates a
human-bootstrapped browser session and raises `ReauthenticationRequired`
when it is missing/invalid/expired; the live fetch (`SessionTransport`) is
hard-gated on the kill switch being off, not running under CI, and
`alliance_access_approved` (false by default — a deliberate per-environment
opt-in after the pre-first-request review). Credential mode is refused
because permission for automated credential login has not been established.

The connector never holds credentials or session contents as attributes —
its repr is safe to log.
"""

import logging
from datetime import date
from typing import ClassVar

from app.core.config import Settings, get_settings
from app.providers.alliance.config import (
    AllianceMode,
    require_live_allowed,
    resolve_mode,
)
from app.providers.alliance.session import load_session
from app.providers.alliance.transport import AllianceTransport, FixtureTransport
from app.providers.base import ProviderConnector
from app.providers.errors import LiveModeRefused
from app.providers.models import (
    DataOrigin,
    ProviderHealth,
    ProviderResult,
    QueryType,
    ResultType,
)

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class AllianceConnector(ProviderConnector):
    provider_id: ClassVar[str] = "alliance"
    display_name: ClassVar[str] = "Alliance Laundry Systems"

    def __init__(
        self,
        settings: Settings | None = None,
        transport: AllianceTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._mode = resolve_mode(self._settings)
        # Data origin reflects the mode honestly: fixture data is never
        # labelled live. Instance attribute (read via `connector.data_origin`).
        self.data_origin: DataOrigin = (
            DataOrigin.FIXTURE if self._mode is AllianceMode.FIXTURE else DataOrigin.LIVE
        )
        self._transport = transport

    def __repr__(self) -> str:
        # Safe to log: mode and provider id only, never paths or secrets.
        return f"AllianceConnector(mode={self._mode.value})"

    async def search(self, query: str, query_type: QueryType) -> list[ProviderResult]:
        records = await self._records_for(query, query_type)
        return [self._normalise(record) for record in records]

    async def _records_for(self, query: str, query_type: QueryType) -> list[dict]:
        if self._mode is AllianceMode.FIXTURE:
            transport = self._transport or FixtureTransport()
            return await transport.search_raw(query, query_type)

        if self._mode is AllianceMode.CREDENTIAL:
            # Not implemented: permission for automated credential login has
            # not been established (access record UNKNOWN/unreviewed).
            # Credentials are never read here.
            raise LiveModeRefused("automated credential login is not established as permitted")

        # Session mode. Validate the session first (pure-local; raises
        # ReauthenticationRequired on missing/invalid/expired) so that outcome
        # is reported even before the access gate.
        load_session(self._settings.alliance_session_path)
        # Only now would a live request happen — gate it hard (kill switch,
        # CI, and the access-approved flag, which is false by default).
        require_live_allowed(self._settings)
        transport = self._transport or self._build_session_transport()
        return await transport.search_raw(query, query_type)

    def _build_session_transport(self) -> AllianceTransport:
        """Construct the authenticated live transport. Reached only after the
        live gate passes; imports httpx lazily so fixture/CI paths never need
        it."""
        import httpx

        from app.providers.alliance.ratelimit import RateLimiter
        from app.providers.alliance.session import load_cookies_for_transport
        from app.providers.alliance.transport import SessionTransport

        cookies = load_cookies_for_transport(self._settings.alliance_session_path)
        jar = httpx.Cookies()
        for cookie in cookies:
            jar.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )
        # Client timeout is the larger download budget; searches are
        # additionally bounded by the registry's per-provider timeout.
        client = httpx.AsyncClient(
            cookies=jar,
            timeout=self._settings.alliance_download_timeout_seconds,
            follow_redirects=False,  # detect login redirects rather than follow
        )
        return SessionTransport(
            client=client,
            allowed_hosts=self._settings.alliance_allowed_host_list,
            rate_limiter=RateLimiter(self._settings.alliance_rate_limit_per_minute),
            max_retries=self._settings.alliance_max_retries,
            max_concurrency=self._settings.alliance_max_concurrency,
            max_retry_after_seconds=self._settings.alliance_max_retry_after_seconds,
            max_response_bytes=self._settings.alliance_max_response_bytes,
            max_document_bytes=self._settings.alliance_max_document_bytes,
            search_url_template=self._settings.alliance_search_url,
        )

    def _normalise(self, record: dict) -> ProviderResult:
        source_path = record.get("source_path")
        return ProviderResult(
            provider_id=self.provider_id,
            source_reference=record["source_reference"],
            result_type=ResultType(record.get("result_type", "document")),
            data_origin=self.data_origin,
            title=record["title"],
            description=record.get("description"),
            manufacturer=record.get("manufacturer"),
            brand=record.get("brand"),
            model=record.get("model"),
            serial_range=record.get("serial_range"),
            document_type=record.get("document_type"),
            part_number=record.get("part_number"),
            revision=record.get("revision"),
            published_at=_parse_date(record.get("published_at")),
            source_url=f"https://portal.alliancels.net{source_path}" if source_path else None,
            access_method="provider_portal",
        )

    async def health_check(self) -> ProviderHealth:
        if self._mode is AllianceMode.FIXTURE:
            return ProviderHealth(status="ok", detail="fixture mode (no live access)")
        if self._mode is AllianceMode.CREDENTIAL:
            return ProviderHealth(status="failed", detail="credential mode not implemented")
        # Session mode: report reachability of a valid session without a
        # network call; never expose session details.
        try:
            load_session(self._settings.alliance_session_path)
        except Exception:
            return ProviderHealth(status="failed", detail="no valid session")
        return ProviderHealth(status="ok", detail="session present")

    async def validate_credentials(self) -> bool:
        # No credentials are handled by this connector. Fixture mode needs
        # none; session mode depends on a human-bootstrapped session.
        if self._mode is AllianceMode.FIXTURE:
            return True
        try:
            load_session(self._settings.alliance_session_path)
        except Exception:
            return False
        return True
