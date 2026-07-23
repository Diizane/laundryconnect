"""Health endpoints.

- /health       basic status for humans and simple monitors
- /health/live  liveness probe: the process is up
- /health/ready readiness probe: dependencies are reachable

The database check reports "skipped" until PostgreSQL integration lands in
Milestone 4 — readiness must reflect reality, not aspiration.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.health import (
    HealthStatus,
    LivenessStatus,
    ReadinessCheck,
    ReadinessStatus,
)

router = APIRouter(prefix="/health", tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("", response_model=HealthStatus)
async def health(settings: SettingsDep) -> HealthStatus:
    return HealthStatus(status="ok", version=__version__, environment=settings.environment)


@router.get("/live", response_model=LivenessStatus)
async def liveness() -> LivenessStatus:
    return LivenessStatus(status="alive")


@router.get("/ready", response_model=ReadinessStatus)
async def readiness(settings: SettingsDep) -> ReadinessStatus:
    checks = [
        ReadinessCheck(
            name="database",
            status="skipped",
            detail="Database integration arrives in Milestone 4; no check performed.",
        )
    ]
    ready = all(check.status != "failed" for check in checks)
    return ReadinessStatus(status="ready" if ready else "not_ready", checks=checks)
