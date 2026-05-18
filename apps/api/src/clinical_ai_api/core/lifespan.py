from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from clinical_ai_platform.core.config import get_settings
from clinical_ai_platform.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger = structlog.get_logger(__name__)

    logger.info(
        "api_starting",
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
    )
    app.state.settings = settings

    yield

    logger.info("api_stopping", app_name=settings.app_name)

