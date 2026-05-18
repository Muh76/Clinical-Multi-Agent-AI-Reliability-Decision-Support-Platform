from fastapi import APIRouter, Response, status

from clinical_ai_api.api.dependencies import HealthServiceDep, RequestIdDep
from clinical_ai_api.schemas.health import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Service health")
async def health(service: HealthServiceDep, request_id: RequestIdDep) -> HealthResponse:
    return await service.get_health(request_id=request_id)


@router.get("/live", response_model=HealthResponse, summary="Liveness probe")
async def liveness(service: HealthServiceDep, request_id: RequestIdDep) -> HealthResponse:
    return await service.get_liveness(request_id=request_id)


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def readiness(
    response: Response,
    service: HealthServiceDep,
    request_id: RequestIdDep,
) -> HealthResponse:
    health_response = await service.get_readiness(request_id=request_id)
    if health_response.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_response
