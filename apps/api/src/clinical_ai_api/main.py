from fastapi import FastAPI

from clinical_ai_api.api.router import api_router
from clinical_ai_api.core.errors import register_exception_handlers
from clinical_ai_api.core.lifespan import lifespan
from clinical_ai_api.middleware import register_middleware
from clinical_ai_platform.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        docs_url="/docs" if settings.api.enable_docs else None,
        redoc_url="/redoc" if settings.api.enable_docs else None,
        openapi_url="/openapi.json" if settings.api.enable_docs else None,
        lifespan=lifespan,
    )
    register_middleware(app)
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
