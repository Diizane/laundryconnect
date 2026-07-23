"""Provider registry and fan-out search.

The registry owns configured connectors and runs searches across all enabled
providers in parallel, with a per-provider timeout. Partial failure is a
first-class outcome: one provider failing or timing out never fails the
search, it is simply reported in the per-provider status list.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.core.config import Settings
from app.providers.base import ProviderConnector
from app.providers.mock.connector import MockProviderConnector
from app.providers.models import (
    AggregatedSearch,
    ProviderOutcome,
    ProviderResult,
    ProviderSearchStatus,
    QueryType,
)

logger = logging.getLogger(__name__)

# Connectors that can be enabled via the ENABLED_PROVIDERS setting.
# Real connectors (alliance, girbau, richard_jay) register here as they are
# implemented (Milestone 8 onwards).
PROVIDER_FACTORIES: dict[str, type[ProviderConnector]] = {
    MockProviderConnector.provider_id: MockProviderConnector,
}


@dataclass
class RegisteredProvider:
    connector: ProviderConnector
    enabled: bool = True


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, RegisteredProvider] = {}

    def register(self, connector: ProviderConnector, enabled: bool = True) -> None:
        if connector.provider_id in self._providers:
            raise ValueError(f"Provider '{connector.provider_id}' is already registered")
        self._providers[connector.provider_id] = RegisteredProvider(connector, enabled)

    def get(self, provider_id: str) -> RegisteredProvider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise KeyError(f"Provider '{provider_id}' is not registered") from None

    def all(self) -> list[RegisteredProvider]:
        return list(self._providers.values())

    async def search_all(
        self, query: str, query_type: QueryType, timeout_seconds: float
    ) -> AggregatedSearch:
        """Search every registered provider in parallel.

        Disabled providers are reported as such without being called. Each
        enabled provider gets its own timeout so a slow provider delays the
        response by at most `timeout_seconds`.
        """
        registered = self.all()
        outcomes_and_results = await asyncio.gather(
            *(self._search_one(entry, query, query_type, timeout_seconds) for entry in registered)
        )
        results: list[ProviderResult] = []
        outcomes: list[ProviderOutcome] = []
        for outcome, provider_results in outcomes_and_results:
            outcomes.append(outcome)
            results.extend(provider_results)
        return AggregatedSearch(results=results, providers=outcomes)

    async def _search_one(
        self,
        entry: RegisteredProvider,
        query: str,
        query_type: QueryType,
        timeout_seconds: float,
    ) -> tuple[ProviderOutcome, list[ProviderResult]]:
        provider_id = entry.connector.provider_id
        if not entry.enabled:
            return (
                ProviderOutcome(provider_id=provider_id, status=ProviderSearchStatus.DISABLED),
                [],
            )

        started = time.perf_counter()

        def latency_ms() -> float:
            return round((time.perf_counter() - started) * 1000, 2)

        try:
            results = await asyncio.wait_for(
                entry.connector.search(query, query_type), timeout_seconds
            )
        except TimeoutError:
            logger.warning(
                "provider search timed out",
                extra={"provider": provider_id, "timeout_seconds": timeout_seconds},
            )
            return (
                ProviderOutcome(
                    provider_id=provider_id,
                    status=ProviderSearchStatus.TIMED_OUT,
                    latency_ms=latency_ms(),
                    error="TimeoutError",
                ),
                [],
            )
        except Exception as exc:
            # Full detail goes to the server log only; the outcome carries just
            # the exception class name in case the message contains anything
            # sensitive from a provider response.
            logger.exception("provider search failed", extra={"provider": provider_id})
            return (
                ProviderOutcome(
                    provider_id=provider_id,
                    status=ProviderSearchStatus.FAILED,
                    latency_ms=latency_ms(),
                    error=type(exc).__name__,
                ),
                [],
            )

        return (
            ProviderOutcome(
                provider_id=provider_id,
                status=ProviderSearchStatus.SUCCESS,
                latency_ms=latency_ms(),
                result_count=len(results),
            ),
            results,
        )


def build_registry(settings: Settings) -> ProviderRegistry:
    """Build the registry from ENABLED_PROVIDERS.

    Unknown provider ids fail fast at startup — a typo in configuration should
    be loud, not a silently missing provider.
    """
    registry = ProviderRegistry()
    for provider_id in settings.enabled_provider_list:
        factory = PROVIDER_FACTORIES.get(provider_id)
        if factory is None:
            known = ", ".join(sorted(PROVIDER_FACTORIES)) or "(none)"
            raise ValueError(
                f"Unknown provider '{provider_id}' in ENABLED_PROVIDERS; known: {known}"
            )
        registry.register(factory())
        logger.info("provider registered", extra={"provider": provider_id})
    return registry
