from fastapi import APIRouter, status

from clinical_ai_api.api.dependencies import RequestIdDep, SafetyServiceDep
from clinical_ai_api.schemas.base import ApiResponse
from clinical_ai_api.schemas.safety import SafetyAssessmentRequest, SafetyAssessmentResponse

router = APIRouter()


@router.post(
    "/assess",
    response_model=ApiResponse[SafetyAssessmentResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a safety assessment",
)
async def assess_safety(
    payload: SafetyAssessmentRequest,
    service: SafetyServiceDep,
    request_id: RequestIdDep,
) -> ApiResponse[SafetyAssessmentResponse]:
    assessment = await service.assess(payload=payload)
    return ApiResponse.from_data(data=assessment, request_id=request_id)

