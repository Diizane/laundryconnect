"""LaundryConnect API application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.database.session import create_engine, create_session_factory
from app.providers.registry import build_registry
from app.schemas.health import ApiMetadata

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    if app.state.db_engine is not None:
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.state.provider_registry = build_registry(settings)

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
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

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
