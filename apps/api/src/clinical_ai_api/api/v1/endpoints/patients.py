from fastapi import APIRouter, status

from clinical_ai_api.api.dependencies import PatientServiceDep, RequestIdDep
from clinical_ai_api.schemas.base import CollectionResponse
from clinical_ai_api.schemas.patients import PatientSummary

router = APIRouter()


@router.get(
    "",
    response_model=CollectionResponse[PatientSummary],
    status_code=status.HTTP_200_OK,
    summary="List patient reliability contexts",
)
async def list_patients(
    service: PatientServiceDep,
    request_id: RequestIdDep,
) -> CollectionResponse[PatientSummary]:
    patients = await service.list_patients()
    return CollectionResponse.from_data(data=patients, request_id=request_id)

