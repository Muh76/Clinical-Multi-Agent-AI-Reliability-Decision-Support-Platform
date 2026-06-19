from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from clinical_ai_api.core.agent_container import (
    build_agent_container,
    close_agent_container,
    warmup_agent_container,
)
from clinical_ai_platform.cache import close_redis, init_redis
from clinical_ai_platform.core.config import get_settings
from clinical_ai_platform.db import close_database, init_database
from clinical_ai_platform.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger = structlog.get_logger(__name__)

    logger.info(
        "api_starting",
        app_name=settings.app.name,
        app_version=settings.app.version,
        environment=settings.app.environment,
    )
    app.state.settings = settings
    init_database(settings)
    init_redis(settings)

    agent_container = build_agent_container(settings)
    app.state.agent_container = agent_container
    await warmup_agent_container(agent_container)

    try:
        yield
    finally:
        await close_agent_container(agent_container)
        app.state.agent_container = None
        await close_redis()
        await close_database()
        logger.info("api_stopping", app_name=settings.app.name)
