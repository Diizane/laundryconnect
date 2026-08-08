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

from app.providers.errors import ProviderDocumentsUnsupported
from app.providers.models import (
    DataOrigin,
    ProviderDocumentInfo,
    ProviderHealth,
    ProviderResult,
    QueryType,
)


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

    # -- Document capability (Milestone 9) — optional per provider ----------

    async def discover_documents(self, reference: str) -> list[ProviderDocumentInfo]:
        """List the documents available for one search result's document
        reference. Implementers MUST validate `reference` against a strict
        provider-local format before any request (it may originate from a
        client) and MUST keep traversal bounded — no crawling. Default:
        unsupported.
        """
        raise ProviderDocumentsUnsupported(
            f"provider '{self.provider_id}' does not support document retrieval"
        )

    async def fetch_document(
        self, source_path: str, *, conditional: dict[str, str] | None = None
    ) -> bytes:
        """Return one validated document's bytes for a `source_path` from
        this provider's own `ProviderDocumentInfo`. Implementers MUST
        validate the path shape (fail closed) and MUST return only validated
        document content. `conditional` carries HTTP validators for cache
        revalidation; implementations that support it raise `NotModified`
        when the provider reports 304. Default: unsupported."""
        raise ProviderDocumentsUnsupported(
            f"provider '{self.provider_id}' does not support document retrieval"
        )
