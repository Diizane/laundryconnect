import pytest

from app.core.config import Settings
from app.providers.mock.connector import MockProviderConnector
from app.providers.models import ProviderSearchStatus, QueryType
from app.providers.registry import ProviderRegistry, build_registry


def test_register_and_get() -> None:
    registry = ProviderRegistry()
    connector = MockProviderConnector()
    registry.register(connector)
    assert registry.get("mock").connector is connector
    assert len(registry.all()) == 1


def test_duplicate_registration_rejected() -> None:
    registry = ProviderRegistry()
    registry.register(MockProviderConnector())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MockProviderConnector())


def test_get_unknown_provider_raises() -> None:
    with pytest.raises(KeyError, match="not registered"):
        ProviderRegistry().get("nope")


def test_build_registry_from_settings() -> None:
    settings = Settings(_env_file=None, enabled_providers="mock")
    registry = build_registry(settings)
    assert [entry.connector.provider_id for entry in registry.all()] == ["mock"]


def test_build_registry_unknown_provider_fails_fast() -> None:
    settings = Settings(_env_file=None, enabled_providers="mock,typo_provider")
    with pytest.raises(ValueError, match="Unknown provider 'typo_provider'"):
        build_registry(settings)


async def test_search_all_success() -> None:
    registry = ProviderRegistry()
    registry.register(MockProviderConnector())
    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5.0)

    assert aggregated.results
    [outcome] = aggregated.providers
    assert outcome.status == ProviderSearchStatus.SUCCESS
    assert outcome.result_count == len(aggregated.results)
    assert outcome.latency_ms is not None


class SecondMockConnector(MockProviderConnector):
    """A second connector id so tests can register two providers at once."""

    provider_id = "failing"


async def test_search_all_partial_failure() -> None:
    """One provider failing must not lose the other provider's results."""
    registry = ProviderRegistry()
    registry.register(MockProviderConnector())
    registry.register(SecondMockConnector(fail_with=RuntimeError("secret provider detail")))

    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5.0)

    statuses = {o.provider_id: o for o in aggregated.providers}
    assert statuses["mock"].status == ProviderSearchStatus.SUCCESS
    assert statuses["failing"].status == ProviderSearchStatus.FAILED
    # Only the exception class name is exposed, never the message.
    assert statuses["failing"].error == "RuntimeError"
    assert "secret provider detail" not in aggregated.model_dump_json()
    assert aggregated.results  # mock's results survived


async def test_search_all_timeout() -> None:
    registry = ProviderRegistry()
    slow = MockProviderConnector(latency_seconds=0.5)
    registry.register(slow)

    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=0.05)

    [outcome] = aggregated.providers
    assert outcome.status == ProviderSearchStatus.TIMED_OUT
    assert outcome.error == "TimeoutError"
    assert aggregated.results == []


async def test_search_all_reports_forbidden_distinctly() -> None:
    from app.providers.errors import ProviderForbidden

    class ForbiddenConnector(MockProviderConnector):
        provider_id = "forbidden_one"

        async def search(self, query: str, query_type: QueryType):
            raise ProviderForbidden("access refused")

    registry = ProviderRegistry()
    registry.register(MockProviderConnector())
    registry.register(ForbiddenConnector())

    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5.0)
    statuses = {o.provider_id: o for o in aggregated.providers}
    assert statuses["mock"].status == ProviderSearchStatus.SUCCESS
    assert statuses["forbidden_one"].status == ProviderSearchStatus.FORBIDDEN
    assert statuses["forbidden_one"].error == "ProviderForbidden"
    assert aggregated.results  # the other provider's results survive


async def test_search_all_disabled_provider_not_called() -> None:
    registry = ProviderRegistry()
    registry.register(
        MockProviderConnector(fail_with=RuntimeError("must never be called")), enabled=False
    )

    aggregated = await registry.search_all("SC60", QueryType.AUTO, timeout_seconds=5.0)

    [outcome] = aggregated.providers
    assert outcome.status == ProviderSearchStatus.DISABLED
    assert outcome.error is None
    assert aggregated.results == []
