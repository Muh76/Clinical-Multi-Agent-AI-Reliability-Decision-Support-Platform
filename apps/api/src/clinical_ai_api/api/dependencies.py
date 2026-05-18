from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header

from clinical_ai_api.services.evaluation import EvaluationService
from clinical_ai_api.services.health import HealthService
from clinical_ai_api.services.patients import PatientService
from clinical_ai_api.services.safety import SafetyService
from clinical_ai_platform.core.config import Settings, get_settings


def get_app_settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


async def get_request_id(x_request_id: Annotated[str | None, Header()] = None) -> str:
    return x_request_id or str(uuid4())


RequestIdDep = Annotated[str, Depends(get_request_id)]


async def get_health_service(settings: SettingsDep) -> HealthService:
    return HealthService(settings=settings)


async def get_patient_service() -> PatientService:
    return PatientService()


async def get_safety_service() -> SafetyService:
    return SafetyService()


async def get_evaluation_service() -> EvaluationService:
    return EvaluationService()


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
SafetyServiceDep = Annotated[SafetyService, Depends(get_safety_service)]
EvaluationServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]

