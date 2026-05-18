from pydantic import BaseModel, Field


class EvaluationRunRequest(BaseModel):
    case_id: str = Field(min_length=1)
    evaluator_name: str = Field(min_length=1)
    dataset_version: str | None = None


class EvaluationRunResponse(BaseModel):
    run_id: str
    status: str
    case_id: str
    evaluator_name: str

