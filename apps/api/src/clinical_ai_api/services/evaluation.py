from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_api.schemas.evaluation import EvaluationRunRequest, EvaluationRunResponse


class EvaluationService:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def list_runs(self) -> list[EvaluationRunResponse]:
        return []

    async def create_run(self, *, payload: EvaluationRunRequest) -> EvaluationRunResponse:
        return EvaluationRunResponse(
            run_id=str(uuid4()),
            status="queued",
            case_id=payload.case_id,
            evaluator_name=payload.evaluator_name,
        )
