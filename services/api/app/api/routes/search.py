"""Unified search endpoint."""

from fastapi import APIRouter

from app.api.deps import SearchServiceDep
from app.schemas.search import SearchRequest, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest, service: SearchServiceDep) -> SearchResponse:
    """Search all enabled providers.

    Results are normalised, deduplicated, ranked, and grouped by machine.
    Per-provider outcomes (including failures and timeouts) are reported in
    `providers` — a failing provider never fails the search.
    """
    return await service.execute(request)
