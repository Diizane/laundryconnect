"""Alliance connector: fixture mode, contract conformance, fixture hygiene."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.alliance.connector import AllianceConnector
from app.providers.base import ProviderConnector
from app.providers.models import DataOrigin, QueryType
from app.tests.connector_contract import ConnectorContract

FIXTURES_DIR = Path(__file__).parent.parent / "providers" / "alliance" / "fixtures"


def _fixture_settings(**overrides: object) -> Settings:
    base = {"_env_file": None, "alliance_mode": "fixture"}
    base.update(overrides)
    return Settings(**base)


class TestAllianceConnectorContract(ConnectorContract):
    known_query = "SC60"

    def make_connector(self) -> ProviderConnector:
        return AllianceConnector(settings=_fixture_settings())


class TestFixtureMode:
    def _connector(self) -> AllianceConnector:
        return AllianceConnector(settings=_fixture_settings())

    async def test_fixture_results_labelled_fixture_not_live(self) -> None:
        results = await self._connector().search("SC60", QueryType.AUTO)
        assert results
        for result in results:
            # Fixture data must NEVER be presented as live.
            assert result.data_origin == DataOrigin.FIXTURE
            assert result.provider_id == "alliance"
            assert result.source_reference

    async def test_part_query(self) -> None:
        results = await self._connector().search("F8524501", QueryType.PART)
        assert len(results) == 1
        assert results[0].part_number == "F8524501"

    async def test_unknown_query_empty(self) -> None:
        assert await self._connector().search("nope-xyz", QueryType.AUTO) == []

    async def test_health_ok_in_fixture_mode(self) -> None:
        health = await self._connector().health_check()
        assert health.status == "ok"

    async def test_source_urls_point_at_portal(self) -> None:
        results = await self._connector().search("SC60", QueryType.MODEL)
        assert all(
            r.source_url is None or r.source_url.startswith("https://portal.alliancels.net")
            for r in results
        )


def test_alliance_fixtures_reviewed() -> None:
    """Every committed fixture must carry human-review metadata (no raw,
    unreviewed provider data)."""
    for fixture in FIXTURES_DIR.glob("*.json"):
        meta = json.loads(fixture.read_text()).get("_meta", {})
        assert meta.get("reviewed_by"), f"{fixture.name} missing _meta.reviewed_by"
        assert meta.get("date"), f"{fixture.name} missing _meta.date"


def test_committed_fixtures_have_no_credential_markers() -> None:
    """Defence in depth: no cookie/token/session material in fixtures."""
    for fixture in FIXTURES_DIR.glob("*.json"):
        text = fixture.read_text().lower()
        for marker in ("set-cookie", "authorization", "password", "sessionid", "bearer "):
            assert marker not in text, f"{fixture.name} contains {marker!r}"


@pytest.mark.parametrize("query_type", list(QueryType))
async def test_search_never_raises_on_valid_queries(query_type: QueryType) -> None:
    connector = AllianceConnector(settings=_fixture_settings())
    # Should return a list for any query type, never raise, in fixture mode.
    assert isinstance(await connector.search("SC60", query_type), list)
