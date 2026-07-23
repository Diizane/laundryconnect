"""Health endpoints.

- /health       basic status for humans and simple monitors
- /health/live  liveness probe: the process is up
- /health/ready readiness probe: dependencies are reachable

The database check runs a real `SELECT 1` when a database is configured and
reports "skipped" when none is — readiness reflects reality either way.
"""

import asyncio

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app import __version__
from app.api.deps import SettingsDep
from app.schemas.health import (
    HealthStatus,
    LivenessStatus,
    ReadinessCheck,
    ReadinessStatus,
)

router = APIRouter(prefix="/health", tags=["health"])

_DB_CHECK_TIMEOUT_SECONDS = 5.0


@router.get("", response_model=HealthStatus)
async def health(settings: SettingsDep) -> HealthStatus:
    return HealthStatus(status="ok", version=__version__, environment=settings.environment)


@router.get("/live", response_model=LivenessStatus)
async def liveness() -> LivenessStatus:
    return LivenessStatus(status="alive")


async def _check_database(request: Request) -> ReadinessCheck:
    engine = request.app.state.db_engine
    if engine is None:
        return ReadinessCheck(name="database", status="skipped", detail="No database configured.")
    try:
        async with asyncio.timeout(_DB_CHECK_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as exc:
        # Connection errors may embed DSNs/credentials — expose the class only.
        return ReadinessCheck(name="database", status="failed", detail=type(exc).__name__)
    return ReadinessCheck(name="database", status="ok")


@router.get("/ready", response_model=ReadinessStatus)
async def readiness(request: Request, response: Response) -> ReadinessStatus:
    checks = [await _check_database(request)]
    ready = all(check.status != "failed" for check in checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessStatus(status="ready" if ready else "not_ready", checks=checks)
