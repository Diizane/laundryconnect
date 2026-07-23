"""Provider connector base interface.

Every provider integration subclasses `ProviderConnector`. The contract is
deliberately small for Milestone 2 (search + health); document/part/model
retrieval methods join the interface in Milestones 6-8 when the features that
consume them exist — no dead stubs before then.

Rules for implementers:

- Return normalised `ProviderResult` models, never provider-specific shapes.
- Authenticate only on the backend; credentials come from settings/secret
  manager, are never logged, and must never appear in exception messages
  (exception text may surface in server logs).
- Set `data_origin` honestly: mock/manual data must never claim to be live.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.providers.models import DataOrigin, ProviderHealth, ProviderResult, QueryType


class ProviderConnector(ABC):
    """Interface all provider connectors implement."""

    provider_id: ClassVar[str]
    display_name: ClassVar[str]
    data_origin: ClassVar[DataOrigin]

    @abstractmethod
    async def search(self, query: str, query_type: QueryType) -> list[ProviderResult]:
        """Search this provider and return normalised results.

        Raise an exception on failure; the registry converts it into a
        per-provider outcome so one provider never breaks the whole search.
        """

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Cheap check that the provider is reachable/usable."""

    async def validate_credentials(self) -> bool:
        """Whether configured credentials work. Default: none required."""
        return True
