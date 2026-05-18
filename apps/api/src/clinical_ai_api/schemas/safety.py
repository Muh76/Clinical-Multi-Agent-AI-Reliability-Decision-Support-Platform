from pydantic import BaseModel, Field


class SafetyAssessmentRequest(BaseModel):
    case_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class SafetyAssessmentResponse(BaseModel):
    assessment_id: str
    status: str
    risk_level: str
    requires_human_review: bool

