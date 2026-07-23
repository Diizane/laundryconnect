"""Contract suite applied to the mock connector.

Every future provider connector gets its own subclass of ConnectorContract
(driven by recorded fixtures) — see connector_contract.py.
"""

from app.providers.base import ProviderConnector
from app.providers.mock.connector import MockProviderConnector
from app.tests.connector_contract import ConnectorContract


class TestMockConnectorContract(ConnectorContract):
    known_query = "SC60"

    def make_connector(self) -> ProviderConnector:
        return MockProviderConnector()
