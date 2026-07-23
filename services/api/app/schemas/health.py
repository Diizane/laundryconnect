"""Response schemas for health and metadata endpoints."""

from typing import Literal

from pydantic import BaseModel


class ApiMetadata(BaseModel):
    name: str
    version: str
    environment: str
    docs_url: str | None


class HealthStatus(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str


class LivenessStatus(BaseModel):
    status: Literal["alive"]


class ReadinessCheck(BaseModel):
    name: str
    status: Literal["ok", "skipped", "failed"]
    detail: str | None = None


class ReadinessStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: list[ReadinessCheck]
