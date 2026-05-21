from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutputAudience(StrEnum):
    CLINICIAN_DASHBOARD = "clinician_dashboard"
    SAFETY_CRITIC = "safety_critic"
    AUDIT = "audit"
    EVALUATION = "evaluation"
    OBSERVABILITY = "observability"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNKNOWN = "unknown"


class ContributionDirection(StrEnum):
    INCREASES_RISK = "increases_risk"
    DECREASES_RISK = "decreases_risk"
    SUPPORTS_EVIDENCE = "supports_evidence"
    CONTRADICTS_EVIDENCE = "contradicts_evidence"
    CONTEXTUAL = "contextual"
    UNKNOWN = "unknown"


class ExplainabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkflowTraceLink(ExplainabilityModel):
    workflow_id: str
    trace_id: str
    case_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    agent_run_ids: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)


class EvidenceAttribution(ExplainabilityModel):
    evidence_id: str
    citation_id: str
    source_id: str
    source_type: str
    title: str | None = None
    url: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    section_path: list[str] = Field(default_factory=list)
    quote: str | None = Field(default=None, max_length=1_000)
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_reliability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    attribution_text: str


class ConfidenceRepresentation(ExplainabilityModel):
    score: float = Field(ge=0.0, le=1.0)
    band: ConfidenceBand = ConfidenceBand.UNKNOWN
    components: dict[str, float] = Field(default_factory=dict)
    rationale: str | None = None
    calibration_notes: list[str] = Field(default_factory=list)


class ReasoningMetadata(ExplainabilityModel):
    reasoning_id: str
    summary: str
    method: str
    input_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    risk_factor_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModalityContribution(ExplainabilityModel):
    modality: str
    present: bool
    record_count: int = Field(ge=0)
    contribution_direction: ContributionDirection = ContributionDirection.UNKNOWN
    contribution_score: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    missingness_notes: list[str] = Field(default_factory=list)


class RiskContributionSummary(ExplainabilityModel):
    factor_id: str
    severity: str
    summary: str
    contribution_score: float = Field(ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None


class CitationFormat(ExplainabilityModel):
    citation_id: str
    display_text: str
    source_label: str
    inline_marker: str
    url: str | None = None


class ExplainableOutput(ExplainabilityModel):
    output_id: str
    output_type: str
    audience: list[OutputAudience]
    trace: WorkflowTraceLink
    summary: str | None = None
    evidence_attributions: list[EvidenceAttribution] = Field(default_factory=list)
    confidence: ConfidenceRepresentation
    reasoning_metadata: list[ReasoningMetadata] = Field(default_factory=list)
    modality_contributions: list[ModalityContribution] = Field(default_factory=list)
    risk_contributions: list[RiskContributionSummary] = Field(default_factory=list)
    citations: list[CitationFormat] = Field(default_factory=list)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def citation_display_text(attribution: EvidenceAttribution) -> str:
    title = attribution.title or attribution.source_id
    year = f" ({attribution.publication_year})" if attribution.publication_year else ""
    source = attribution.source_type.replace("_", " ")
    section = f", {' > '.join(attribution.section_path)}" if attribution.section_path else ""
    return f"{title}{year}. {source}: {attribution.source_id}{section}."


def format_citation(attribution: EvidenceAttribution, index: int) -> CitationFormat:
    return CitationFormat(
        citation_id=attribution.citation_id,
        display_text=citation_display_text(attribution),
        source_label=attribution.title or attribution.source_id,
        inline_marker=f"[{index}]",
        url=attribution.url,
    )


def attach_formatted_citations(output: ExplainableOutput) -> ExplainableOutput:
    citations = [
        format_citation(attribution, index)
        for index, attribution in enumerate(output.evidence_attributions, start=1)
    ]
    return output.model_copy(update={"citations": citations})


def serialize_explainable_output(output: ExplainableOutput) -> dict[str, Any]:
    return attach_formatted_citations(output).model_dump(mode="json")


def serialize_explainable_output_json(output: ExplainableOutput) -> str:
    return attach_formatted_citations(output).model_dump_json()


def redacted_observability_payload(output: ExplainableOutput) -> dict[str, Any]:
    formatted = attach_formatted_citations(output)
    return {
        "output_id": formatted.output_id,
        "output_type": formatted.output_type,
        "audience": [audience.value for audience in formatted.audience],
        "workflow_id": formatted.trace.workflow_id,
        "trace_id": formatted.trace.trace_id,
        "case_id": formatted.trace.case_id,
        "confidence_score": formatted.confidence.score,
        "confidence_band": formatted.confidence.band.value,
        "evidence_count": len(formatted.evidence_attributions),
        "citation_count": len(formatted.citations),
        "risk_contribution_count": len(formatted.risk_contributions),
        "modality_count": len(formatted.modality_contributions),
        "created_at": formatted.created_at.isoformat(),
    }
