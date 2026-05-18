from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_api.schemas.safety import SafetyAssessmentRequest, SafetyAssessmentResponse


class SafetyService:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def assess(self, *, payload: SafetyAssessmentRequest) -> SafetyAssessmentResponse:
        return SafetyAssessmentResponse(
            assessment_id=str(uuid4()),
            status="queued",
            risk_level="unknown",
            requires_human_review=True,
        )
