"""Reusable contract tests every ProviderConnector implementation must pass.

Usage — subclass in the provider's test module and provide the hooks:

    class TestAllianceConnectorContract(ConnectorContract):
        known_query = "SC60"

        def make_connector(self) -> ProviderConnector:
            return AllianceConnector(transport=fixture_transport("alliance"))

Real connectors must be driven by RECORDED FIXTURES here (see
fixtures/providers/README.md) — the contract suite runs in CI and must
never call a live provider service.
"""

import re

from app.providers.base import ProviderConnector
from app.providers.models import DataOrigin, ProviderResult, QueryType

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SECRET_MARKERS = ("password", "secret", "token", "cookie", "authorization")


class ConnectorContract:
    """Inherit and provide `make_connector()` plus `known_query`."""

    # A query guaranteed (by fixtures) to return at least one result.
    known_query: str
    known_query_type: QueryType = QueryType.AUTO

    def make_connector(self) -> ProviderConnector:
        raise NotImplementedError

    def test_identity_is_declared(self) -> None:
        connector = self.make_connector()
        assert _SLUG_RE.match(connector.provider_id), "provider_id must be a slug"
        assert connector.display_name.strip()
        assert isinstance(connector.data_origin, DataOrigin)

    async def test_search_returns_normalised_results(self) -> None:
        connector = self.make_connector()
        results = await connector.search(self.known_query, self.known_query_type)
        assert results, f"fixtures must yield results for {self.known_query!r}"
        for result in results:
            assert isinstance(result, ProviderResult)
            assert result.provider_id == connector.provider_id
            assert result.data_origin == connector.data_origin
            assert result.source_reference.strip(), "source traceability is mandatory"
            assert result.title.strip()

    async def test_unknown_query_returns_empty_not_error(self) -> None:
        connector = self.make_connector()
        results = await connector.search("zzz-contract-no-such-thing-9x9", QueryType.AUTO)
        assert results == []

    async def test_health_check_reports_status(self) -> None:
        connector = self.make_connector()
        health = await connector.health_check()
        assert health.status in ("ok", "failed")

    async def test_validate_credentials_returns_bool(self) -> None:
        connector = self.make_connector()
        assert isinstance(await connector.validate_credentials(), bool)

    def test_no_secret_material_in_repr(self) -> None:
        """repr/str must be log-safe: no credential-looking key material."""
        connector = self.make_connector()
        for text in (repr(connector), str(connector)):
            lowered = text.lower()
            for marker in _SECRET_MARKERS:
                assert f"{marker}=" not in lowered and f"{marker}':" not in lowered, (
                    f"connector repr leaks a value for '{marker}'"
                )
