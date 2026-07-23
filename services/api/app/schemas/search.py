"""Request/response schemas for unified search."""

from pydantic import BaseModel, Field, field_validator

from app.providers.models import ProviderOutcome, ProviderResult, QueryType

MAX_QUERY_LENGTH = 200


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    query_type: QueryType = QueryType.AUTO

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class MachineGroup(BaseModel):
    """Results grouped under one machine/model (or 'other' when unknown)."""

    manufacturer: str | None
    brand: str | None
    model: str | None
    results: list[ProviderResult]


class SearchResponse(BaseModel):
    query: str
    requested_query_type: QueryType
    detected_query_type: QueryType
    total_results: int
    groups: list[MachineGroup]
    providers: list[ProviderOutcome]
