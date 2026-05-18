from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_api.services.evaluation import EvaluationService
from clinical_ai_api.services.health import HealthService
from clinical_ai_api.services.patients import PatientService
from clinical_ai_api.services.safety import SafetyService
from clinical_ai_platform.cache import CacheService, get_redis
from clinical_ai_platform.core.config import Settings, get_settings
from clinical_ai_platform.db import get_session


def get_app_settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
AsyncSessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def get_request_id(
    request: Request,
    x_request_id: Annotated[str | None, Header()] = None,
) -> str:
    state_request_id = getattr(request.state, "request_id", None)
    return state_request_id or x_request_id or str(uuid4())


RequestIdDep = Annotated[str, Depends(get_request_id)]


async def get_cache_service(settings: SettingsDep, redis: RedisDep) -> CacheService:
    return CacheService(redis=redis, key_prefix=settings.redis.key_prefix)


async def get_health_service(settings: SettingsDep, redis: RedisDep) -> HealthService:
    return HealthService(settings=settings, redis=redis)


async def get_patient_service(session: AsyncSessionDep) -> PatientService:
    return PatientService(session=session)


async def get_safety_service(session: AsyncSessionDep) -> SafetyService:
    return SafetyService(session=session)


async def get_evaluation_service(session: AsyncSessionDep) -> EvaluationService:
    return EvaluationService(session=session)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
CacheServiceDep = Annotated[CacheService, Depends(get_cache_service)]
PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
SafetyServiceDep = Annotated[SafetyService, Depends(get_safety_service)]
EvaluationServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
