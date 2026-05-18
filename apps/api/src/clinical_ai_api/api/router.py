from fastapi import APIRouter

from clinical_ai_api.api.v1.router import router as v1_router
from clinical_ai_api.api.v1.endpoints.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(v1_router, prefix="/api/v1")

