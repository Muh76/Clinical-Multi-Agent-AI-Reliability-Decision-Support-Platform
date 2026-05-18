from fastapi import APIRouter, status

from clinical_ai_api.api.dependencies import EvaluationServiceDep, RequestIdDep
from clinical_ai_api.schemas.base import ApiResponse, CollectionResponse
from clinical_ai_api.schemas.evaluation import EvaluationRunRequest, EvaluationRunResponse

router = APIRouter()


@router.get(
    "/runs",
    response_model=CollectionResponse[EvaluationRunResponse],
    status_code=status.HTTP_200_OK,
    summary="List evaluation runs",
)
async def list_evaluation_runs(
    service: EvaluationServiceDep,
    request_id: RequestIdDep,
) -> CollectionResponse[EvaluationRunResponse]:
    runs = await service.list_runs()
    return CollectionResponse.from_data(data=runs, request_id=request_id)


@router.post(
    "/runs",
    response_model=ApiResponse[EvaluationRunResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create an evaluation run",
)
async def create_evaluation_run(
    payload: EvaluationRunRequest,
    service: EvaluationServiceDep,
    request_id: RequestIdDep,
) -> ApiResponse[EvaluationRunResponse]:
    run = await service.create_run(payload=payload)
    return ApiResponse.from_data(data=run, request_id=request_id)

