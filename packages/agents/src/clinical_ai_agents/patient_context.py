from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from clinical_ai_agents.contracts import (
    AgentFinding,
    AgentInput,
    AgentOutput,
    AgentRole,
    AgentRunStatus,
    ConfidenceBand,
    ConfidenceScore,
)
from clinical_ai_agents.temporal import summarize_timeline
from clinical_ai_multimodal.patient_context import PatientContextProcessor
from clinical_ai_multimodal.patient_context.schemas import (
    ModalityContext,
    ModalityType,
    RawPatientContext,
    StructuredPatientContext,
    ValidationFinding,
    ValidationSeverity,
)
from clinical_ai_platform.observability import get_logger
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class ModalitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    modality: str
    present: bool
    record_count: int = Field(ge=0)
    missing_field_count: int = Field(ge=0)
    quality_finding_count: int = Field(ge=0)


class PatientContextAgentRepresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    patient_id: str
    context_id: str
    generated_at: datetime
    modality_summaries: list[ModalitySummary]
    temporal_summary: dict[str, Any] = Field(default_factory=dict)
    missingness_summary: dict[str, Any] = Field(default_factory=dict)
    retrieval_profile: dict[str, Any] = Field(default_factory=dict)
    explainability_profile: dict[str, Any] = Field(default_factory=dict)
    safety_profile: dict[str, Any] = Field(default_factory=dict)
    modality_fusion_inputs: dict[str, Any] = Field(default_factory=dict)
    validation_findings: list[dict[str, Any]] = Field(default_factory=list)


class PatientContextAgent:
    name = "patient_context_agent"
    role = AgentRole.PATIENT_CONTEXT

    def __init__(self, processor: PatientContextProcessor | None = None) -> None:
        self._processor = processor or PatientContextProcessor()

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started_at = datetime.now(UTC)
        start = perf_counter()
        logger.info(
            "agent_run_started",
            agent_name=self.name,
            agent_role=self.role.value,
            agent_run_id=agent_input.trace.agent_run_id,
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            case_id=agent_input.case_id,
        )
        try:
            raw_context = parse_patient_context(agent_input.payload)
            structured_context = self._processor.process(raw_context)
            representation = build_patient_representation(structured_context)
            confidence = build_confidence(structured_context, representation)
            findings = agent_findings(structured_context.validation_findings)
            status = (
                AgentRunStatus.REQUIRES_REVIEW
                if any(finding.requires_human_review for finding in findings)
                else AgentRunStatus.COMPLETED
            )
            output = AgentOutput(
                case_id=agent_input.case_id,
                role=self.role,
                status=status,
                trace=agent_input.trace,
                summary=patient_summary(representation),
                structured_payload={
                    "patient_representation": representation.model_dump(mode="json"),
                    "structured_patient_context": structured_context.model_dump(mode="json"),
                },
                findings=findings,
                confidence=confidence,
                citations=[],
                explainability={
                    "source_systems": structured_context.unified.explainability_profile.get(
                        "source_systems",
                        [],
                    ),
                    "available_modalities": structured_context.unified.explainability_profile.get(
                        "available_modalities",
                        [],
                    ),
                    "timeline_event_count": len(structured_context.unified.timeline),
                },
                safety_hooks={
                    "requires_human_review": status == AgentRunStatus.REQUIRES_REVIEW,
                    "validation_finding_count": len(structured_context.validation_findings),
                    "missingness_summary": representation.missingness_summary,
                    "safe_for_diagnosis_prediction": False,
                },
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception(
                "agent_run_failed",
                agent_name=self.name,
                agent_role=self.role.value,
                agent_run_id=agent_input.trace.agent_run_id,
                workflow_id=agent_input.trace.workflow_id,
                trace_id=agent_input.trace.trace_id,
                case_id=agent_input.case_id,
            )
            raise

        logger.info(
            "agent_run_completed",
            agent_name=self.name,
            agent_role=self.role.value,
            agent_run_id=agent_input.trace.agent_run_id,
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            case_id=agent_input.case_id,
            status=output.status.value,
            confidence_score=output.confidence.score,
            confidence_band=output.confidence.band.value,
            latency_ms=round((perf_counter() - start) * 1000, 2),
            validation_finding_count=len(output.findings),
        )
        return output


def parse_patient_context(payload: dict[str, Any]) -> RawPatientContext:
    if "patient_context" in payload:
        return RawPatientContext.model_validate(payload["patient_context"])
    return RawPatientContext.model_validate(payload)


def build_patient_representation(
    structured_context: StructuredPatientContext,
) -> PatientContextAgentRepresentation:
    modality_contexts = structured_context.unified.modality_contexts
    return PatientContextAgentRepresentation(
        patient_id=structured_context.patient_id,
        context_id=structured_context.context_id,
        generated_at=structured_context.generated_at,
        modality_summaries=[
            modality_summary(modality_context)
            for modality_context in sorted(
                modality_contexts.values(),
                key=lambda context: context.modality.value,
            )
        ],
        temporal_summary=summarize_timeline(structured_context.unified.timeline),
        missingness_summary=missingness_summary(modality_contexts),
        retrieval_profile=structured_context.unified.retrieval_profile,
        explainability_profile=structured_context.unified.explainability_profile,
        safety_profile=structured_context.unified.safety_profile,
        modality_fusion_inputs=modality_fusion_inputs(structured_context),
        validation_findings=[
            finding.model_dump(mode="json")
            for finding in structured_context.validation_findings
        ],
    )


def modality_summary(context: ModalityContext) -> ModalitySummary:
    return ModalitySummary(
        modality=context.modality.value,
        present=context.present,
        record_count=context.record_count,
        missing_field_count=len(context.missing_fields),
        quality_finding_count=len(context.quality_findings),
    )


def missingness_summary(
    modality_contexts: dict[ModalityType, ModalityContext],
) -> dict[str, Any]:
    missing_by_modality = {
        modality.value: len(context.missing_fields)
        for modality, context in modality_contexts.items()
    }
    absent_modalities = [
        modality.value
        for modality, context in modality_contexts.items()
        if not context.present
    ]
    return {
        "missing_field_count": sum(missing_by_modality.values()),
        "missing_by_modality": missing_by_modality,
        "absent_modalities": sorted(absent_modalities),
    }


def modality_fusion_inputs(
    structured_context: StructuredPatientContext,
) -> dict[str, Any]:
    modality_contexts = structured_context.unified.modality_contexts
    return {
        "context_id": structured_context.context_id,
        "patient_id": structured_context.patient_id,
        "available_modalities": sorted(
            modality.value
            for modality, context in modality_contexts.items()
            if context.present
        ),
        "record_counts": {
            modality.value: context.record_count
            for modality, context in modality_contexts.items()
        },
        "timeline_event_count": len(structured_context.unified.timeline),
        "retrieval_terms": structured_context.unified.retrieval_profile.get("query_terms", []),
        "note_types": structured_context.unified.retrieval_profile.get("note_types", []),
        "fusion_ready": any(context.present for context in modality_contexts.values()),
    }


def build_confidence(
    structured_context: StructuredPatientContext,
    representation: PatientContextAgentRepresentation,
) -> ConfidenceScore:
    modality_coverage = coverage_score(representation.modality_summaries)
    temporal_score = float(representation.temporal_summary.get("temporal_completeness", 0.0))
    validation_score = validation_quality_score(structured_context.validation_findings)
    missingness_score = missingness_quality_score(representation)
    provenance_score = provenance_quality_score(structured_context)
    score = clamp01(
        0.25 * modality_coverage
        + 0.25 * temporal_score
        + 0.20 * validation_score
        + 0.15 * missingness_score
        + 0.15 * provenance_score
    )
    return ConfidenceScore(
        score=score,
        band=confidence_band(score),
        components={
            "modality_coverage": modality_coverage,
            "temporal_completeness": temporal_score,
            "validation_quality": validation_score,
            "missingness_quality": missingness_score,
            "provenance_quality": provenance_score,
        },
        rationale=confidence_rationale(score, structured_context.validation_findings),
    )


def coverage_score(summaries: list[ModalitySummary]) -> float:
    core_modalities = {
        "demographics",
        "vitals",
        "labs",
        "medications",
        "clinical_notes",
        "imaging_metadata",
    }
    present = {summary.modality for summary in summaries if summary.present}
    return len(core_modalities & present) / len(core_modalities)


def validation_quality_score(findings: list[ValidationFinding]) -> float:
    if not findings:
        return 1.0
    penalty = 0.0
    for finding in findings:
        if finding.severity == ValidationSeverity.ERROR:
            penalty += 0.30
        elif finding.severity == ValidationSeverity.WARNING:
            penalty += 0.15
        else:
            penalty += 0.03
    return clamp01(1.0 - penalty)


def missingness_quality_score(representation: PatientContextAgentRepresentation) -> float:
    missing_count = int(representation.missingness_summary.get("missing_field_count", 0))
    absent_count = len(representation.missingness_summary.get("absent_modalities", []))
    return clamp01(1.0 - (0.04 * missing_count) - (0.08 * absent_count))


def provenance_quality_score(structured_context: StructuredPatientContext) -> float:
    records = [
        *structured_context.normalized.vitals,
        *structured_context.normalized.labs,
        *structured_context.normalized.medications,
        *structured_context.normalized.clinical_notes,
        *structured_context.normalized.imaging_metadata,
    ]
    if structured_context.normalized.demographics is not None:
        records.append(structured_context.normalized.demographics)
    if not records:
        return 0.0
    with_provenance = sum(1 for record in records if record.provenance is not None)
    return with_provenance / len(records)


def confidence_band(score: float) -> ConfidenceBand:
    if score >= 0.85:
        return ConfidenceBand.HIGH
    if score >= 0.65:
        return ConfidenceBand.MODERATE
    if score > 0.0:
        return ConfidenceBand.LOW
    return ConfidenceBand.UNKNOWN


def confidence_rationale(score: float, findings: list[ValidationFinding]) -> str:
    if any(finding.severity == ValidationSeverity.ERROR for finding in findings):
        return "Patient context contains validation errors and should be reviewed."
    if score >= 0.85:
        return "Patient context is well structured with strong temporal and modality coverage."
    if score >= 0.65:
        return "Patient context is usable, with some missingness or provenance limitations."
    return (
        "Patient context is incomplete or weakly timestamped; downstream agents should be "
        "cautious."
    )


def agent_findings(findings: list[ValidationFinding]) -> list[AgentFinding]:
    return [
        AgentFinding(
            code=finding.code,
            severity=finding.severity.value,
            message=finding.message,
            evidence_refs=[finding.field_path] if finding.field_path else [],
            requires_human_review=finding.severity == ValidationSeverity.ERROR,
        )
        for finding in findings
    ]


def patient_summary(representation: PatientContextAgentRepresentation) -> str:
    available = [
        summary.modality
        for summary in representation.modality_summaries
        if summary.present
    ]
    absent = representation.missingness_summary.get("absent_modalities", [])
    return (
        "Structured patient context prepared for downstream reliability workflows. "
        f"Available modalities: {', '.join(available) if available else 'none'}. "
        f"Absent modalities: {', '.join(absent) if absent else 'none'}. "
        f"Timeline events: {representation.temporal_summary.get('event_count', 0)}."
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
