from clinical_ai_api.schemas.patients import PatientSummary


class PatientService:
    async def list_patients(self) -> list[PatientSummary]:
        return []

