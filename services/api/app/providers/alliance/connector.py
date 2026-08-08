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
import re
from datetime import date
from typing import ClassVar

from app.core.config import Settings, get_settings
from app.providers.alliance.config import (
    AllianceMode,
    require_live_allowed,
    resolve_mode,
)
from app.providers.alliance.document_parser import parse_literature_page, parse_manual_page
from app.providers.alliance.session import load_session
from app.providers.alliance.transport import AllianceTransport, FixtureTransport
from app.providers.base import ProviderConnector
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentReference,
    LiveModeRefused,
)
from app.providers.models import (
    DataOrigin,
    ProviderDocumentInfo,
    ProviderHealth,
    ProviderResult,
    QueryType,
    ResultType,
)

logger = logging.getLogger(__name__)

# Document reference from search-result metadata: '<ManualId>:<ModelId>',
# digits only. Validated before any request is built.
_DOCUMENT_REF = re.compile(r"^(\d{1,12}):(\d{1,12})$")
# The only document location Phase 1 observed. Anything else fails closed.
# Segments must start alphanumeric so dot-only segments ('..') can't match.
_DOCUMENT_PATH = re.compile(
    r"^/manuals/[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9 ._-]*\.pdf$"
)


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

    # -- Document workflow (Milestone 9) -----------------------------------
    #
    # Bounded by design (Phase 1 findings, docs/MILESTONE_9): at most TWO
    # intermediate HTML pages (/en/Manual menu → /en/Model/Literature list)
    # then ONE validated PDF. Never crawls, never recurses, never follows
    # links outside the observed workflow. Nothing is persisted or cached.

    def _document_transport(self) -> AllianceTransport:
        """The transport for document-workflow fetches, mode-gated exactly
        like search: fixture serves local files; session validates the
        session and the live gate first; credential mode is refused."""
        if self._mode is AllianceMode.FIXTURE:
            return self._transport or FixtureTransport()
        if self._mode is AllianceMode.CREDENTIAL:
            raise LiveModeRefused("automated credential login is not established as permitted")
        load_session(self._settings.alliance_session_path)
        require_live_allowed(self._settings)
        return self._transport or self._build_session_transport()

    def _resolve_path(self, path_or_url: str) -> str:
        """Provider-relative paths resolve against the Parts Connection base;
        absolute URLs pass through (the transport's URL policy and host
        allowlist still apply to every fetch)."""
        if path_or_url.startswith("https://") or path_or_url.startswith("http://"):
            return path_or_url
        return f"{self._settings.alliance_parts_base_url}{path_or_url}"

    async def discover_documents(self, reference: str) -> list[ProviderDocumentInfo]:
        """Provider document contract: `reference` is `<ManualId>:<ModelId>`
        (numeric catalog identifiers, as carried in search-result metadata).
        Strictly validated BEFORE any request — a client-supplied reference
        can never inject a URL or path. The manual URL is built server-side.
        """
        match = _DOCUMENT_REF.match(reference or "")
        if match is None:
            raise InvalidDocumentReference(
                "document reference must be '<manual id>:<model id>' (digits only)"
            )
        manual_id, model_id = match.groups()
        return await self._discover_from_manual_path(
            f"/en/Manual?ManualId={manual_id}&ModelId={model_id}"
        )

    async def _discover_from_manual_path(self, manual_path: str) -> list[ProviderDocumentInfo]:
        """From a `/en/Manual?...` link, list the documents the provider
        offers for that model, with metadata. Fetches at most two pages;
        returns metadata only (no document bytes, no persistence)."""
        transport = self._document_transport()
        manual = parse_manual_page(await transport.fetch_page(self._resolve_path(manual_path)))

        records: list[dict] = [
            {
                "part_number": None,
                "document_type": None,
                "comment": None,
                "languages": [],
                "source_path": path,
                "category": None,
                "filename": path.rsplit("/", 1)[-1],
                "available": True,
                "title": path.rsplit("/", 1)[-1],
            }
            for path in manual.direct_pdf_paths
        ]
        if manual.literature_path:
            literature_body = await transport.fetch_page(self._resolve_path(manual.literature_path))
            records.extend(parse_literature_page(literature_body))
        # Traversal ends here — never follow further links (bounded by design).

        return [
            ProviderDocumentInfo(
                provider_id=self.provider_id,
                data_origin=self.data_origin,
                title=record["title"],
                document_type=record["document_type"],
                part_number=record["part_number"],
                comment=record["comment"],
                languages=record["languages"],
                category=record["category"],
                filename=record["filename"],
                source_path=record["source_path"],
                available=record["available"],
            )
            for record in records
        ]

    async def fetch_document(
        self, source_path: str, *, conditional: dict[str, str] | None = None
    ) -> bytes:
        """Fetch ONE document's bytes (validated PDF) via the transport. The
        caller (Phase 3 API) streams these to the client; nothing is
        persisted. The path shape is validated first (pure-local, fail
        closed) so only `/manuals/<Category>/<file>.pdf` paths — the only
        document location Phase 1 observed — can ever reach the transport.
        Raises `DocumentNotFound` / `InvalidDocumentContent` /
        `ReauthenticationRequired` / `ProviderForbidden` as domain outcomes.
        """
        if _DOCUMENT_PATH.match(source_path or "") is None:
            raise DocumentNotFound("no document at this location")
        transport = self._document_transport()
        body = await transport.fetch_document(
            self._resolve_path(source_path), conditional=conditional
        )
        # Surface the provider's cache validators for the caching layer.
        self.last_document_validators = getattr(transport, "last_document_validators", {})
        return body

    def _build_session_transport(self) -> AllianceTransport:
        """Construct the authenticated live transport. Reached only after the
        live gate passes; imports httpx lazily so fixture/CI paths never need
        it."""
        import httpx

        from app.providers.alliance.parser import parse_search_html
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
            serial_search_url_template=self._settings.alliance_serial_search_url,
            parser=parse_search_html,
        )

    def _normalise(self, record: dict) -> ProviderResult:
        # Live records carry a full source_url (Parts Connection); fixture
        # records may carry a portal-relative source_path instead.
        source_url = record.get("source_url")
        if not source_url and record.get("source_path"):
            source_url = f"{self._settings.alliance_base_url}{record['source_path']}"
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
            source_url=source_url,
            access_method="provider_portal",
            metadata=record.get("metadata", {}),
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
