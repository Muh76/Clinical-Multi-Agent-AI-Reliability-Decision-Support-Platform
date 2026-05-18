from fastapi import APIRouter

from clinical_ai_api.api.dependencies import HealthServiceDep, RequestIdDep
from clinical_ai_api.schemas.health import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Service health")
async def health(service: HealthServiceDep, request_id: RequestIdDep) -> HealthResponse:
    return await service.get_health(request_id=request_id)

