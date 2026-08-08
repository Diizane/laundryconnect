"""LaundryConnect API application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_v1_router
from app.core.auth import require_api_key, validate_auth_configuration
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.database.session import create_engine, create_session_factory
from app.providers.alliance.keepalive import SessionKeepalive
from app.providers.registry import build_registry
from app.schemas.health import ApiMetadata

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    keepalive = getattr(app.state, "alliance_keepalive", None)
    if keepalive is not None:
        keepalive.start()
    yield
    if keepalive is not None:
        await keepalive.stop()
    if app.state.db_engine is not None:
        await app.state.db_engine.dispose()


def _build_keepalive(settings) -> SessionKeepalive | None:
    """Wire the keepalive to the real connector's page fetch, lazily so
    fixture/CI paths never construct a live transport."""
    if not settings.alliance_keepalive_enabled:
        return None

    async def fetch_page(url: str) -> bytes:
        from app.providers.alliance.connector import AllianceConnector

        connector = AllianceConnector(settings=settings)
        transport = connector._document_transport()  # noqa: SLF001 - same live gate
        return await transport.fetch_page(url)

    return SessionKeepalive(settings, fetch_page=fetch_page)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Refuse to start an unauthenticated API in production (the backend
    # holds an authenticated provider session).
    validate_auth_configuration(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.state.provider_registry = build_registry(settings)
    app.state.alliance_keepalive = _build_keepalive(settings)

    # The app must start without a database until Milestone 4 environments
    # are established; readiness reporting reflects whichever is the case.
    app.state.db_engine = None
    app.state.db_session_factory = None
    if settings.database_url:
        app.state.db_engine = create_engine(settings.database_url, echo=settings.debug)
        app.state.db_session_factory = create_session_factory(app.state.db_engine)
        logger.info("database engine configured")

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    # Every v1 route requires an API key when keys are configured; the
    # dependency exempts health/liveness/readiness probes itself.
    app.include_router(
        api_v1_router,
        prefix=settings.api_v1_prefix,
        dependencies=[Depends(require_api_key)],
    )

    @app.get("/", response_model=ApiMetadata, tags=["meta"])
    async def root() -> ApiMetadata:
        return ApiMetadata(
            name=settings.app_name,
            version=__version__,
            environment=settings.environment,
            docs_url=app.docs_url,
        )

    logger.info(
        "application configured",
        extra={"environment": settings.environment, "version": __version__},
    )
    return app


app = create_app()
