import pytest

from app.providers.mock.connector import MockProviderConnector
from app.providers.models import DataOrigin, QueryType, ResultType


@pytest.fixture
def connector() -> MockProviderConnector:
    return MockProviderConnector()


async def test_all_results_are_labelled_mock(connector: MockProviderConnector) -> None:
    results = await connector.search("SC60", QueryType.AUTO)
    assert results
    for result in results:
        assert result.data_origin == DataOrigin.MOCK
        assert result.provider_id == "mock"
        assert result.source_reference
        assert result.title


async def test_model_search(connector: MockProviderConnector) -> None:
    results = await connector.search("sc60", QueryType.MODEL)
    assert results
    assert all(result.model == "SC60" for result in results)


async def test_part_search(connector: MockProviderConnector) -> None:
    results = await connector.search("F8524501", QueryType.PART)
    assert len(results) == 1
    assert results[0].result_type == ResultType.PART
    assert results[0].part_number == "F8524501"


async def test_fault_code_search(connector: MockProviderConnector) -> None:
    results = await connector.search("EdL", QueryType.FAULT_CODE)
    assert results
    assert any(result.result_type == ResultType.FAULT_CODE for result in results)


async def test_serial_search(connector: MockProviderConnector) -> None:
    results = await connector.search("2100000", QueryType.SERIAL)
    assert len(results) == 1
    assert results[0].model == "HS-6008"


async def test_no_match_returns_empty(connector: MockProviderConnector) -> None:
    assert await connector.search("does-not-exist-xyz", QueryType.AUTO) == []


async def test_blank_query_returns_empty(connector: MockProviderConnector) -> None:
    assert await connector.search("   ", QueryType.AUTO) == []


async def test_health_check_ok(connector: MockProviderConnector) -> None:
    health = await connector.health_check()
    assert health.status == "ok"


async def test_health_check_with_fault_injection() -> None:
    connector = MockProviderConnector(fail_with=RuntimeError("boom"))
    health = await connector.health_check()
    assert health.status == "failed"
