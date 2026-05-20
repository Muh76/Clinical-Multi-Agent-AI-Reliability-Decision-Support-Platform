from fastapi import APIRouter, Request, status

from clinical_ai_api.api.dependencies import RequestIdDep, WorkflowServiceDep
from clinical_ai_api.schemas.base import ApiResponse
from clinical_ai_api.schemas.workflows import (
    GroundedEvidenceWorkflowRequest,
    GroundedEvidenceWorkflowResponse,
)

router = APIRouter()


@router.post(
    "/evidence-grounding",
    response_model=ApiResponse[GroundedEvidenceWorkflowResponse],
    status_code=status.HTTP_200_OK,
    summary="Run the end-to-end evidence grounding workflow",
)
async def run_evidence_grounding_workflow(
    payload: GroundedEvidenceWorkflowRequest,
    service: WorkflowServiceDep,
    request_id: RequestIdDep,
    request: Request,
) -> ApiResponse[GroundedEvidenceWorkflowResponse]:
    result = await service.run(
        payload=payload,
        request_id=request_id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return ApiResponse.from_data(data=result, request_id=request_id)
