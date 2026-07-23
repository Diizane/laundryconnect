"""Unified search service.

Composes the provider registry fan-out with detection, deduplication,
ranking, and grouping. The `execute` method is a pure request → response
function over the registry, which keeps it directly cacheable: a future
cache layer wraps `execute` keyed on (query, query_type) without touching
this logic (see ADR 0004).
"""

import logging

from app.providers.registry import ProviderRegistry
from app.schemas.search import MachineGroup, SearchRequest, SearchResponse
from app.search.detection import detect_query_type
from app.search.processing import deduplicate, group_by_machine, rank

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, registry: ProviderRegistry, provider_timeout_seconds: float) -> None:
        self._registry = registry
        self._timeout = provider_timeout_seconds

    async def execute(self, request: SearchRequest) -> SearchResponse:
        query = request.query.strip()
        detected = detect_query_type(query, request.query_type)

        aggregated = await self._registry.search_all(query, detected, self._timeout)
        results = rank(deduplicate(aggregated.results), query)
        groups = [
            MachineGroup(manufacturer=manufacturer, brand=brand, model=model, results=group_results)
            for (manufacturer, brand, model), group_results in group_by_machine(results)
        ]

        logger.info(
            "search executed",
            extra={
                "query_type": detected.value,
                "result_count": len(results),
                "provider_count": len(aggregated.providers),
                "failed_providers": [
                    outcome.provider_id
                    for outcome in aggregated.providers
                    if outcome.status not in ("success", "disabled")
                ],
            },
        )

        return SearchResponse(
            query=query,
            requested_query_type=request.query_type,
            detected_query_type=detected,
            total_results=len(results),
            groups=groups,
            providers=aggregated.providers,
        )
