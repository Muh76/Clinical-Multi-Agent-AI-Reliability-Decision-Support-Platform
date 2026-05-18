from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_api.schemas.patients import PatientSummary


class PatientService:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def list_patients(self) -> list[PatientSummary]:
        return []
