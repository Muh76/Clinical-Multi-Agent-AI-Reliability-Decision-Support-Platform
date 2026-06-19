from fastapi import APIRouter, Request, status

from clinical_ai_api.api.dependencies import RequestIdDep, WorkflowServiceDep
from clinical_ai_api.schemas.base import ApiResponse
from clinical_ai_api.schemas.workflows import (
    GroundedEvidenceWorkflowRequest,
    GroundedEvidenceWorkflowResponse,
)

router = APIRouter()


async def _run_clinical_reliability_workflow(
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


@router.post(
    "/clinical-reliability",
    response_model=ApiResponse[GroundedEvidenceWorkflowResponse],
    status_code=status.HTTP_200_OK,
    summary="Run the full safety-aware clinical reliability workflow",
    description=(
        "Single entry point for the end-to-end pipeline: PatientContextAgent, "
        "EvidenceRetrievalAgent, RiskAnalysisAgent, then hallucination detection, "
        "evidence verification, uncertainty scoring, escalation logic, and human "
        "approval evaluation via SafetyAwareClinicalWorkflowRunner."
    ),
)
async def run_clinical_reliability_workflow(
    payload: GroundedEvidenceWorkflowRequest,
    service: WorkflowServiceDep,
    request_id: RequestIdDep,
    request: Request,
) -> ApiResponse[GroundedEvidenceWorkflowResponse]:
    return await _run_clinical_reliability_workflow(payload, service, request_id, request)


@router.post(
    "/evidence-grounding",
    response_model=ApiResponse[GroundedEvidenceWorkflowResponse],
    status_code=status.HTTP_200_OK,
    summary="Run the evidence grounding workflow (alias for clinical-reliability)",
    description=(
        "Backward-compatible alias. Executes the same SafetyAwareClinicalWorkflowRunner "
        "pipeline as POST /workflows/clinical-reliability."
    ),
    deprecated=True,
)
async def run_evidence_grounding_workflow(
    payload: GroundedEvidenceWorkflowRequest,
    service: WorkflowServiceDep,
    request_id: RequestIdDep,
    request: Request,
) -> ApiResponse[GroundedEvidenceWorkflowResponse]:
    return await _run_clinical_reliability_workflow(payload, service, request_id, request)
