"""Version 1 API router.

All v1 routes are aggregated here and mounted under the configured prefix
(`/api/v1` by default). Future route modules (search, machines, documents,
providers, admin) register here as milestones deliver them.
"""

from fastapi import APIRouter

from app.api.routes import documents, health, machines, providers, search

api_v1_router = APIRouter()
api_v1_router.include_router(documents.router)
api_v1_router.include_router(health.router)
api_v1_router.include_router(machines.router)
api_v1_router.include_router(providers.router)
api_v1_router.include_router(search.router)
