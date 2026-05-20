from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from clinical_ai_multimodal.patient_context.schemas import RawPatientContext
from pydantic import BaseModel, ConfigDict, Field


class WorkflowStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str
    text: str = Field(min_length=1, max_length=100_000)
    title: str | None = None
    source_type: str = "synthetic_protocol"
    citation_id: str | None = None
    url: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    evidence_level: str | None = None
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class GroundedEvidenceWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str
    patient_context: RawPatientContext
    evidence_query: str | None = Field(
        default=None,
        description="Optional explicit retrieval query. Defaults to patient context query terms.",
    )
    evidence_corpus: list[EvidenceSourceInput] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)
    enable_reranking: bool = True
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class WorkflowTraceStep(BaseModel):
    name: str
    status: WorkflowStepStatus
    started_at: datetime
    completed_at: datetime
    latency_ms: float = Field(ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowTrace(BaseModel):
    workflow_id: str
    trace_id: str
    request_id: str | None = None
    correlation_id: str | None = None
    started_at: datetime
    completed_at: datetime
    latency_ms: float = Field(ge=0.0)
    steps: list[WorkflowTraceStep]


class EvidenceCitationResponse(BaseModel):
    citation_id: str
    source_id: str
    source_type: str
    title: str | None = None
    url: str | None = None
    publication_year: int | None = None
    quote: str | None = None
    attribution_text: str


class RetrievedEvidenceResponse(BaseModel):
    rank: int = Field(ge=1)
    source_id: str
    source_type: str
    text: str
    citation: EvidenceCitationResponse
    score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    retrieval_score: float = Field(ge=0.0, le=1.0)
    rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_reliability_score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalMetadataResponse(BaseModel):
    query: str
    retrieval_mode: str
    candidate_count: int = Field(ge=0)
    retrieved_count: int = Field(ge=0)
    reranked: bool
    top_k: int = Field(ge=1)
    context_id: str
    patient_id: str
    validation_finding_count: int = Field(ge=0)
    safety_review_recommended: bool


class SafetyCriticIntegrationPoint(BaseModel):
    name: str
    status: str
    required_inputs: list[str]


class GroundedEvidenceWorkflowResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    case_id: str
    patient_id: str
    context_id: str
    evidence: list[RetrievedEvidenceResponse]
    citations: list[EvidenceCitationResponse]
    confidence_score: float = Field(ge=0.0, le=1.0)
    retrieval_metadata: RetrievalMetadataResponse
    trace: WorkflowTrace
    safety_critic_integration_points: list[SafetyCriticIntegrationPoint]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
