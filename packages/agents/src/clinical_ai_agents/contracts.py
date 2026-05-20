from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(StrEnum):
    PATIENT_CONTEXT = "patient_context"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    RISK_ANALYSIS = "risk_analysis"
    SAFETY_CRITIC = "safety_critic"
    EXPLAINABILITY = "explainability"
    AUDIT = "audit"


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REQUIRES_REVIEW = "requires_review"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNKNOWN = "unknown"


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentTraceContext(AgentModel):
    workflow_id: str
    trace_id: str
    agent_run_id: str
    request_id: str | None = None
    correlation_id: str | None = None
    parent_agent_run_id: str | None = None


class AgentInput(AgentModel):
    case_id: str
    role: AgentRole
    trace: AgentTraceContext
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    tool_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ConfidenceScore(AgentModel):
    score: float = Field(ge=0.0, le=1.0)
    band: ConfidenceBand = ConfidenceBand.UNKNOWN
    components: dict[str, float] = Field(default_factory=dict)
    rationale: str | None = None


class AgentFinding(AgentModel):
    code: str
    severity: str
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


class AgentOutput(AgentModel):
    case_id: str
    role: AgentRole
    status: AgentRunStatus
    trace: AgentTraceContext
    summary: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    findings: list[AgentFinding] = Field(default_factory=list)
    confidence: ConfidenceScore = Field(default_factory=lambda: ConfidenceScore(score=0.0))
    citations: list[str] = Field(default_factory=list)
    explainability: dict[str, Any] = Field(default_factory=dict)
    safety_hooks: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClinicalAgent(Protocol):
    name: str
    role: AgentRole

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """Run one traceable agent step and return a structured output."""
