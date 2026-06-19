from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from clinical_ai_agents.end_to_end import (
    EndToEndClinicalReliabilityWorkflowRunner,
    EndToEndWorkflowOutput,
    EndToEndWorkflowRequest,
)
from clinical_ai_platform.observability import get_logger
from clinical_ai_safety import (
    ApprovalWorkflowOutput,
    ApprovalWorkflowRequest,
    ClaimToValidate,
    EscalationPolicy,
    EscalationRequest,
    EscalationSignals,
    EvidenceReference,
    EvidenceVerificationRequest,
    HallucinationDetectionRequest,
    HumanApprovalWorkflowEngine,
    ModalityCompletenessInput,
    ReviewCheckpoint,
    ReviewCheckpointType,
    UncertaintyScoringRequest,
    approval_output,
    create_approval_workflow,
    evaluate_escalation,
    evaluate_hallucination_risk,
    score_uncertainty,
    verify_evidence_support,
)
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class SafetyAwareWorkflowRequest(EndToEndWorkflowRequest):
    safety_policy: EscalationPolicy = Field(default_factory=EscalationPolicy)
    require_human_approval_checkpoint: bool = True


class SafetyCriticEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evaluation_id: str
    status: str
    safety_events: list[dict[str, Any]] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    summary: str


class SafetyAwareWorkflowOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    output_id: str
    workflow_id: str
    trace_id: str
    case_id: str
    status: str
    base_workflow: EndToEndWorkflowOutput
    retrieved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    risk_analysis: dict[str, Any] = Field(default_factory=dict)
    hallucination_risk: dict[str, Any] = Field(default_factory=dict)
    evidence_verification: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    escalation: dict[str, Any] = Field(default_factory=dict)
    safety_critic: dict[str, Any] = Field(default_factory=dict)
    safety_events: list[dict[str, Any]] = Field(default_factory=list)
    approval: dict[str, Any] = Field(default_factory=dict)
    approval_requirements: dict[str, Any] = Field(default_factory=dict)
    explainability_metadata: dict[str, Any] = Field(default_factory=dict)
    workflow_trace_ids: dict[str, str | None] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)
    failure_recovery: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SafetyAwareClinicalWorkflowRunner:
    def __init__(
        self,
        *,
        base_runner: EndToEndClinicalReliabilityWorkflowRunner | None = None,
        approval_engine: HumanApprovalWorkflowEngine | None = None,
    ) -> None:
        self._base_runner = base_runner or EndToEndClinicalReliabilityWorkflowRunner()
        self._approval_engine = approval_engine or HumanApprovalWorkflowEngine()

    async def run(
        self,
        request: SafetyAwareWorkflowRequest,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> SafetyAwareWorkflowOutput:
        logger.info(
            "safety_aware_workflow_started",
            case_id=request.case_id,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        base_output = await self._base_runner.run(
            request,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        safety_output = build_safety_aware_output(
            base_output=base_output,
            policy=request.safety_policy,
            require_human_approval_checkpoint=request.require_human_approval_checkpoint,
        )
        logger.info(
            "safety_aware_workflow_completed",
            output_id=safety_output.output_id,
            workflow_id=safety_output.workflow_id,
            trace_id=safety_output.trace_id,
            case_id=safety_output.case_id,
            status=safety_output.status,
            safety_event_count=len(safety_output.safety_events),
            approval_required=safety_output.approval_requirements.get("required"),
        )
        return safety_output


def build_safety_aware_output(
    *,
    base_output: EndToEndWorkflowOutput,
    policy: EscalationPolicy,
    require_human_approval_checkpoint: bool,
) -> SafetyAwareWorkflowOutput:
    claims = claims_from_risk_analysis(base_output.risk_analysis)
    evidence = evidence_references_from_output(base_output)
    citation_ids = [item.citation_id for item in evidence]

    hallucination_report = evaluate_hallucination_risk(
        HallucinationDetectionRequest(
            case_id=base_output.case_id,
            workflow_id=base_output.workflow_id,
            trace_id=base_output.trace_id,
            claims=claims,
            evidence=evidence,
            available_citation_ids=citation_ids,
            confidence_score=workflow_confidence(base_output),
        )
    )
    verification_report = verify_evidence_support(
        EvidenceVerificationRequest(
            case_id=base_output.case_id,
            workflow_id=base_output.workflow_id,
            trace_id=base_output.trace_id,
            claims=claims,
            evidence=evidence,
            available_citation_ids=citation_ids,
            upstream_confidence=workflow_confidence(base_output),
        )
    )
    uncertainty_report = score_uncertainty(
        UncertaintyScoringRequest(
            case_id=base_output.case_id,
            workflow_id=base_output.workflow_id,
            trace_id=base_output.trace_id,
            retrieval_confidence=retrieval_confidence(base_output),
            grounding_confidence=hallucination_report.grounding_confidence,
            verification_confidence=verification_report.verification_confidence,
            citation_coverage=hallucination_report.citation_coverage,
            evidence_coverage=verification_report.evidence_coverage.evidence_coverage_score,
            source_trust_score=verification_report.source_trust_score,
            risk_analysis_confidence=risk_confidence(base_output),
            risk_factor_count=len(base_output.risk_analysis.get("contributing_factors", [])),
            unstable_trend_count=unstable_trend_count(base_output.risk_analysis),
            contradiction_count=verification_report.contradiction_count,
            temporal_completeness=temporal_completeness(base_output),
            temporal_inconsistency_count=temporal_inconsistency_count(base_output),
            modality_inputs=modality_inputs(base_output),
        )
    )
    escalation_decision = evaluate_escalation(
        EscalationRequest(
            case_id=base_output.case_id,
            workflow_id=base_output.workflow_id,
            trace_id=base_output.trace_id,
            checkpoint_id="pre_output_release",
            policy=policy,
            signals=EscalationSignals(
                hallucination_risk_score=hallucination_report.hallucination_risk_score,
                retrieval_confidence=retrieval_confidence(base_output),
                grounding_confidence=hallucination_report.grounding_confidence,
                verification_confidence=verification_report.verification_confidence,
                uncertainty_score=uncertainty_report.uncertainty_score,
                contradiction_count=verification_report.contradiction_count,
                unsupported_claim_count=len(hallucination_report.unsupported_claims),
                missing_required_modalities=missing_required_modalities(base_output),
                unstable_temporal_trend_count=unstable_trend_count(base_output.risk_analysis),
                upstream_recommendations=[
                    hallucination_report.escalation_recommendation,
                    verification_report.escalation_recommendation,
                    uncertainty_report.escalation_recommendation,
                ],
            ),
        )
    )
    approval_record = None
    if require_human_approval_checkpoint or escalation_decision.human_review_request is not None:
        approval_record = create_approval_workflow(
            ApprovalWorkflowRequest(
                case_id=base_output.case_id,
                workflow_id=base_output.workflow_id,
                trace_id=base_output.trace_id,
                checkpoint=ReviewCheckpoint(
                    checkpoint_id="pre_output_release",
                    checkpoint_type=ReviewCheckpointType.PRE_OUTPUT_RELEASE,
                    name="Pre-output safety approval",
                    required=escalation_decision.interruption.requires_human_review,
                    blocking=not escalation_decision.interruption.allow_downstream_output,
                    queue=policy.review_queue,
                    policy_refs=[policy.policy_id],
                ),
                escalation_decision=escalation_decision,
                human_review_request=escalation_decision.human_review_request,
                summary="Safety-aware workflow requires review before output release.",
                evidence_refs=[item.evidence_id for item in evidence],
                claim_refs=[claim.claim_id for claim in claims],
                modality_refs=missing_required_modalities(base_output),
                confidence_summary={
                    "workflow": workflow_confidence(base_output) or 0.0,
                    "hallucination_grounding": hallucination_report.grounding_confidence,
                    "verification": verification_report.verification_confidence,
                    "uncertainty": uncertainty_report.uncertainty_score,
                },
                risk_summary={
                    "risk_level": base_output.risk_analysis.get("risk_level"),
                    "risk_score": base_output.risk_analysis.get("risk_score"),
                    "escalation_indicator_count": len(base_output.escalation_indicators),
                },
                limitations=workflow_limitations(
                    hallucination_report.failed_checks,
                    verification_report.failed_checks,
                    uncertainty_report.uncertainty_sources,
                ),
            )
        )
    safety_critic = safety_critic_evaluation(
        hallucination_report=hallucination_report.model_dump(mode="json"),
        verification_report=verification_report.model_dump(mode="json"),
        uncertainty_report=uncertainty_report.model_dump(mode="json"),
        escalation_decision=escalation_decision.model_dump(mode="json"),
    )
    safety_events = structured_safety_events(
        safety_critic,
        hallucination_report.model_dump(mode="json"),
        verification_report.model_dump(mode="json"),
        uncertainty_report.model_dump(mode="json"),
        escalation_decision.model_dump(mode="json"),
    )
    approval_payload = (
        approval_output(approval_record).model_dump(mode="json")
        if approval_record is not None
        else ApprovalWorkflowOutput(
            approval_id=f"approval-not-required-{uuid4()}",
            state="not_required",
            allow_workflow_resume=True,
            allow_output_release=True,
            requires_follow_up=False,
        ).model_dump(mode="json")
    )
    status = safety_aware_status(base_output.status, escalation_decision, approval_payload)
    return SafetyAwareWorkflowOutput(
        output_id=f"safety-aware-output-{uuid4()}",
        workflow_id=base_output.workflow_id,
        trace_id=base_output.trace_id,
        case_id=base_output.case_id,
        status=status,
        base_workflow=base_output,
        retrieved_evidence=base_output.retrieved_evidence,
        risk_analysis=base_output.risk_analysis,
        hallucination_risk=hallucination_report.model_dump(mode="json"),
        evidence_verification=verification_report.model_dump(mode="json"),
        uncertainty=uncertainty_report.model_dump(mode="json"),
        escalation=escalation_decision.model_dump(mode="json"),
        safety_critic=safety_critic.model_dump(mode="json"),
        safety_events=safety_events,
        approval=approval_payload,
        approval_requirements=approval_requirements(escalation_decision, approval_payload),
        explainability_metadata=explainability_metadata(
            base_output,
            safety_critic,
            escalation_decision.model_dump(mode="json"),
        ),
        workflow_trace_ids={
            "workflow_id": base_output.workflow_id,
            "trace_id": base_output.trace_id,
            "approval_id": str(approval_payload.get("approval_id")),
        },
        observability=safety_observability_payload(
            base_output,
            hallucination_report.model_dump(mode="json"),
            uncertainty_report.model_dump(mode="json"),
            escalation_decision.model_dump(mode="json"),
            approval_payload,
        ),
        failure_recovery=failure_recovery_plan(status, escalation_decision.model_dump(mode="json")),
    )


def evidence_references_from_output(output: EndToEndWorkflowOutput) -> list[EvidenceReference]:
    citation_by_id = {
        citation.get("citation_id"): citation
        for citation in output.citations
        if isinstance(citation, dict)
    }
    references: list[EvidenceReference] = []
    for index, item in enumerate(output.retrieved_evidence):
        citation_id = str(item.get("citation_id") or item.get("chunk_id") or f"citation-{index}")
        citation = citation_by_id.get(citation_id, {})
        references.append(
            EvidenceReference(
                evidence_id=str(item.get("chunk_id") or item.get("document_id") or citation_id),
                citation_id=citation_id,
                text=str(item.get("text") or citation.get("quote") or ""),
                source_id=str(
                    item.get("source_id")
                    or item.get("document_id")
                    or citation.get("source_id")
                    or citation_id
                ),
                source_type=str(
                    item.get("source_type")
                    or item.get("metadata", {}).get("source_type")
                    or citation.get("source_type")
                    or "unknown"
                ),
                title=item.get("title") or citation.get("title"),
                reliability_score=float(item.get("source_reliability_score", 0.5)),
                relevance_score=float(item.get("score", item.get("confidence_score", 0.0))),
                metadata={
                    "evidence_level": item.get("metadata", {}).get("evidence_level"),
                    "publication_year": citation.get("publication_year"),
                },
            )
        )
    return references


def claims_from_risk_analysis(risk_analysis: dict[str, Any]) -> list[ClaimToValidate]:
    claims: list[ClaimToValidate] = []
    for index, factor in enumerate(risk_analysis.get("contributing_factors", [])):
        if not isinstance(factor, dict):
            continue
        citation_ids = [
            str(ref)
            for ref in [
                *factor.get("evidence_refs", []),
                *risk_analysis.get("evidence_references", []),
            ]
            if ref
        ]
        claims.append(
            ClaimToValidate(
                claim_id=str(factor.get("code") or f"risk-factor-{index}"),
                text=str(factor.get("message") or factor.get("code") or "Risk factor."),
                citation_ids=sorted(set(citation_ids)),
                claim_type="risk_factor",
                source_refs=[str(ref) for ref in factor.get("source_refs", [])],
                metadata={"severity": factor.get("severity")},
            )
        )
    if not claims and risk_analysis:
        claims.append(
            ClaimToValidate(
                claim_id="risk-analysis-summary",
                text=f"Risk analysis level is {risk_analysis.get('risk_level', 'unknown')}.",
                citation_ids=[str(ref) for ref in risk_analysis.get("evidence_references", [])],
                claim_type="risk_summary",
            )
        )
    return claims


def safety_critic_evaluation(
    *,
    hallucination_report: dict[str, Any],
    verification_report: dict[str, Any],
    uncertainty_report: dict[str, Any],
    escalation_decision: dict[str, Any],
) -> SafetyCriticEvaluation:
    failed_checks = [
        *hallucination_report.get("failed_checks", []),
        *verification_report.get("failed_checks", []),
    ]
    safety_events = escalation_decision.get("events", [])
    status = "passed"
    if escalation_decision.get("recommended_action") in {"block", "human_review"}:
        status = "requires_review"
    if escalation_decision.get("recommended_action") == "block":
        status = "blocked"
    return SafetyCriticEvaluation(
        evaluation_id=f"safety-critic-evaluation-{uuid4()}",
        status=status,
        safety_events=safety_events,
        failed_checks=sorted(set(map(str, failed_checks))),
        summary=(
            "Safety Critic evaluation composed hallucination, verification, uncertainty, "
            "and escalation outputs."
        ),
    )


def structured_safety_events(
    *reports: dict[str, Any] | SafetyCriticEvaluation,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for report in reports:
        payload = report.model_dump(mode="json") if isinstance(report, BaseModel) else report
        for event in payload.get("events", []):
            if isinstance(event, dict):
                events.append(event)
        for check in payload.get("failed_checks", []):
            events.append({"event_type": "failed_check", "code": check})
    return events


def workflow_confidence(output: EndToEndWorkflowOutput) -> float | None:
    value = output.confidence_scores.get("workflow")
    return float(value) if isinstance(value, int | float) else None


def retrieval_confidence(output: EndToEndWorkflowOutput) -> float | None:
    agent_score = output.confidence_scores.get("agents", {}).get("evidence_retrieval", {})
    value = agent_score.get("score")
    return float(value) if isinstance(value, int | float) else None


def risk_confidence(output: EndToEndWorkflowOutput) -> float | None:
    agent_score = output.confidence_scores.get("agents", {}).get("risk_analysis", {})
    value = agent_score.get("score")
    return float(value) if isinstance(value, int | float) else None


def modality_inputs(output: EndToEndWorkflowOutput) -> list[ModalityCompletenessInput]:
    patient = output.structured_patient_context.get("unified", {})
    contexts = patient.get("modality_contexts", {})
    inputs: list[ModalityCompletenessInput] = []
    for modality, context in contexts.items():
        if not isinstance(context, dict):
            continue
        inputs.append(
            ModalityCompletenessInput(
                modality=str(modality),
                present=bool(context.get("present", False)),
                required=True,
                record_count=int(context.get("record_count", 0)),
                missing_field_count=len(context.get("missing_fields", [])),
                quality_issue_count=len(context.get("quality_findings", [])),
            )
        )
    return inputs


def missing_required_modalities(output: EndToEndWorkflowOutput) -> list[str]:
    patient = output.structured_patient_context.get("unified", {})
    contexts = patient.get("modality_contexts", {})
    return sorted(
        str(modality)
        for modality, context in contexts.items()
        if isinstance(context, dict) and not context.get("present", False)
    )


def unstable_trend_count(risk_analysis: dict[str, Any]) -> int:
    return sum(
        1
        for signal in risk_analysis.get("trend_signals", [])
        if isinstance(signal, dict) and signal.get("direction") in {"increasing", "decreasing"}
    )


def temporal_completeness(output: EndToEndWorkflowOutput) -> float | None:
    summary = output.structured_patient_context.get("unified", {}).get("temporal_summary", {})
    value = summary.get("temporal_completeness")
    return float(value) if isinstance(value, int | float) else None


def temporal_inconsistency_count(output: EndToEndWorkflowOutput) -> int:
    findings = output.structured_patient_context.get("validation_findings", [])
    return sum(
        1
        for finding in findings
        if isinstance(finding, dict) and "timestamp" in str(finding.get("code", "")).lower()
    )


def workflow_limitations(*groups: list[str]) -> list[str]:
    limitations: list[str] = []
    for group in groups:
        limitations.extend(str(item) for item in group)
    return sorted(set(limitations))


def approval_requirements(
    escalation_decision: Any,
    approval_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "required": escalation_decision.interruption.requires_human_review,
        "blocking": not escalation_decision.interruption.allow_downstream_output,
        "state": approval_payload.get("state"),
        "allow_workflow_resume": approval_payload.get("allow_workflow_resume"),
        "allow_output_release": approval_payload.get("allow_output_release"),
    }


def explainability_metadata(
    base_output: EndToEndWorkflowOutput,
    safety_critic: SafetyCriticEvaluation,
    escalation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "base_explainability": base_output.explainability,
        "safety_critic_status": safety_critic.status,
        "safety_failed_checks": safety_critic.failed_checks,
        "escalation_trigger_types": escalation.get("observability", {}).get("trigger_types", []),
        "trace_linkage": {
            "workflow_id": base_output.workflow_id,
            "trace_id": base_output.trace_id,
            "case_id": base_output.case_id,
        },
    }


def safety_observability_payload(
    base_output: EndToEndWorkflowOutput,
    hallucination_report: dict[str, Any],
    uncertainty_report: dict[str, Any],
    escalation_decision: dict[str, Any],
    approval_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workflow_id": base_output.workflow_id,
        "trace_id": base_output.trace_id,
        "case_id": base_output.case_id,
        "base_status": base_output.status,
        "hallucination_risk_score": hallucination_report.get("hallucination_risk_score"),
        "uncertainty_score": uncertainty_report.get("uncertainty_score"),
        "escalation_action": escalation_decision.get("recommended_action"),
        "safety_event_count": len(escalation_decision.get("events", [])),
        "approval_state": approval_payload.get("state"),
        "approval_required": approval_payload.get("requires_follow_up")
        or not approval_payload.get("allow_output_release", True),
    }


def failure_recovery_plan(status: str, escalation_decision: dict[str, Any]) -> dict[str, Any]:
    if status == "blocked":
        next_step = "Do not release output; route to safety or governance review."
    elif status == "requires_review":
        next_step = "Pause workflow until human approval decision is recorded."
    elif status == "qualified":
        next_step = "Release only with explicit reliability qualification."
    else:
        next_step = "No recovery action required."
    return {
        "status": status,
        "next_step": next_step,
        "retryable": status not in {"blocked"},
        "escalation_action": escalation_decision.get("recommended_action"),
    }


def safety_aware_status(
    base_status: str,
    escalation_decision: Any,
    approval_payload: dict[str, Any],
) -> str:
    if base_status == "failed":
        return "failed"
    if escalation_decision.recommended_action.value == "block":
        return "blocked"
    if escalation_decision.recommended_action.value == "human_review":
        return "requires_review"
    if escalation_decision.recommended_action.value == "qualify":
        return "qualified"
    if not approval_payload.get("allow_output_release", True):
        return "requires_review"
    return "completed"
