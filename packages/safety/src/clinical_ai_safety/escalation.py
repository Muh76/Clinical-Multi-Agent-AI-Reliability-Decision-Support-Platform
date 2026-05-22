from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from clinical_ai_safety.hallucination import EscalationRecommendation


class EscalationSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationTriggerType(StrEnum):
    HALLUCINATION_RISK = "hallucination_risk"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    LOW_RETRIEVAL_CONFIDENCE = "low_retrieval_confidence"
    MISSING_MODALITY = "missing_modality"
    UNSTABLE_TEMPORAL_TREND = "unstable_temporal_trend"
    HIGH_UNCERTAINTY = "high_uncertainty"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    LOW_GROUNDING_CONFIDENCE = "low_grounding_confidence"
    LOW_VERIFICATION_CONFIDENCE = "low_verification_confidence"
    WORKFLOW_FAILURE = "workflow_failure"


class WorkflowInterruptionAction(StrEnum):
    CONTINUE = "continue"
    CONTINUE_WITH_QUALIFICATION = "continue_with_qualification"
    PAUSE_FOR_HUMAN_REVIEW = "pause_for_human_review"
    BLOCK_OUTPUT = "block_output"


class EscalationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EscalationThresholds(EscalationModel):
    hallucination_risk_human_review: float = Field(default=0.55, ge=0.0, le=1.0)
    hallucination_risk_block: float = Field(default=0.80, ge=0.0, le=1.0)
    retrieval_confidence_minimum: float = Field(default=0.55, ge=0.0, le=1.0)
    grounding_confidence_minimum: float = Field(default=0.60, ge=0.0, le=1.0)
    verification_confidence_minimum: float = Field(default=0.65, ge=0.0, le=1.0)
    uncertainty_human_review: float = Field(default=0.55, ge=0.0, le=1.0)
    uncertainty_block: float = Field(default=0.80, ge=0.0, le=1.0)
    max_contradictions_before_block: int = Field(default=2, ge=1)
    max_unsupported_claims_before_review: int = Field(default=1, ge=1)
    max_missing_required_modalities_before_review: int = Field(default=1, ge=1)
    max_unstable_trends_before_review: int = Field(default=2, ge=1)


class EscalationPolicy(EscalationModel):
    policy_id: str = "clinical-reliability-default"
    version: str = "v1"
    enabled: bool = True
    thresholds: EscalationThresholds = Field(default_factory=EscalationThresholds)
    review_queue: str = "clinical_safety_review"
    governance_queue: str = "ai_governance_review"
    require_review_for_any_contradiction: bool = True
    block_on_critical_hallucination: bool = True
    block_on_repeated_contradictions: bool = True
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class EscalationSignals(EscalationModel):
    hallucination_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    retrieval_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    grounding_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    verification_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty_score: float | None = Field(default=None, ge=0.0, le=1.0)
    contradiction_count: int = Field(default=0, ge=0)
    unsupported_claim_count: int = Field(default=0, ge=0)
    missing_required_modalities: list[str] = Field(default_factory=list)
    unstable_temporal_trend_count: int = Field(default=0, ge=0)
    workflow_failure_count: int = Field(default=0, ge=0)
    upstream_recommendations: list[EscalationRecommendation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationRequest(EscalationModel):
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    checkpoint_id: str = "safety_checkpoint"
    policy: EscalationPolicy = Field(default_factory=EscalationPolicy)
    signals: EscalationSignals = Field(default_factory=EscalationSignals)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationEvent(EscalationModel):
    event_id: str
    trigger_type: EscalationTriggerType
    severity: EscalationSeverity
    action: WorkflowInterruptionAction
    message: str
    threshold: float | int | None = None
    observed_value: float | int | str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    modality_refs: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    review_queue: str | None = None
    policy_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanReviewRequest(EscalationModel):
    review_id: str
    queue: str
    priority: EscalationSeverity
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    reason: str
    blocking: bool
    event_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowInterruptionDecision(EscalationModel):
    action: WorkflowInterruptionAction
    should_interrupt: bool
    allow_downstream_output: bool
    requires_human_review: bool
    qualification_required: bool
    reason: str


class EscalationDecision(EscalationModel):
    decision_id: str
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    checkpoint_id: str
    policy_id: str
    policy_version: str
    recommended_action: EscalationRecommendation
    interruption: WorkflowInterruptionDecision
    events: list[EscalationEvent] = Field(default_factory=list)
    human_review_request: HumanReviewRequest | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EscalationPolicyEngine:
    def evaluate(self, request: EscalationRequest) -> EscalationDecision:
        return evaluate_escalation(request)


def evaluate_escalation(request: EscalationRequest) -> EscalationDecision:
    if not request.policy.enabled:
        return disabled_policy_decision(request)

    events = escalation_events(request)
    interruption = interruption_decision(events)
    recommendation = recommendation_from_action(interruption.action)
    review_request = human_review_request(request, events, interruption)
    return EscalationDecision(
        decision_id=f"escalation-decision-{uuid4()}",
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        checkpoint_id=request.checkpoint_id,
        policy_id=request.policy.policy_id,
        policy_version=request.policy.version,
        recommended_action=recommendation,
        interruption=interruption,
        events=events,
        human_review_request=review_request,
        audit_metadata=audit_metadata(request, events, interruption),
        observability=observability_payload(request, events, interruption),
    )


def escalation_events(request: EscalationRequest) -> list[EscalationEvent]:
    signals = request.signals
    thresholds = request.policy.thresholds
    events: list[EscalationEvent] = []

    events.extend(hallucination_events(request, signals, thresholds))
    events.extend(contradiction_events(request, signals, thresholds))
    events.extend(confidence_events(request, signals, thresholds))
    events.extend(uncertainty_events(request, signals, thresholds))
    events.extend(context_events(request, signals, thresholds))
    events.extend(upstream_recommendation_events(request))
    return events


def hallucination_events(
    request: EscalationRequest,
    signals: EscalationSignals,
    thresholds: EscalationThresholds,
) -> list[EscalationEvent]:
    if signals.hallucination_risk_score is None:
        return []
    if (
        request.policy.block_on_critical_hallucination
        and signals.hallucination_risk_score >= thresholds.hallucination_risk_block
    ):
        return [
            event(
                request,
                EscalationTriggerType.HALLUCINATION_RISK,
                EscalationSeverity.CRITICAL,
                WorkflowInterruptionAction.BLOCK_OUTPUT,
                "Hallucination risk exceeds blocking threshold.",
                thresholds.hallucination_risk_block,
                signals.hallucination_risk_score,
            )
        ]
    if signals.hallucination_risk_score >= thresholds.hallucination_risk_human_review:
        return [
            event(
                request,
                EscalationTriggerType.HALLUCINATION_RISK,
                EscalationSeverity.HIGH,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Hallucination risk exceeds human-review threshold.",
                thresholds.hallucination_risk_human_review,
                signals.hallucination_risk_score,
            )
        ]
    return []


def contradiction_events(
    request: EscalationRequest,
    signals: EscalationSignals,
    thresholds: EscalationThresholds,
) -> list[EscalationEvent]:
    if not signals.contradiction_count:
        return []
    action = (
        WorkflowInterruptionAction.BLOCK_OUTPUT
        if request.policy.block_on_repeated_contradictions
        and signals.contradiction_count >= thresholds.max_contradictions_before_block
        else WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW
    )
    return [
        event(
            request,
            EscalationTriggerType.CONTRADICTORY_EVIDENCE,
            EscalationSeverity.CRITICAL
            if action == WorkflowInterruptionAction.BLOCK_OUTPUT
            else EscalationSeverity.HIGH,
            action,
            "Contradictory evidence or reasoning signals are present.",
            thresholds.max_contradictions_before_block,
            signals.contradiction_count,
        )
    ]


def confidence_events(
    request: EscalationRequest,
    signals: EscalationSignals,
    thresholds: EscalationThresholds,
) -> list[EscalationEvent]:
    events: list[EscalationEvent] = []
    if (
        signals.retrieval_confidence is not None
        and signals.retrieval_confidence < thresholds.retrieval_confidence_minimum
    ):
        events.append(
            event(
                request,
                EscalationTriggerType.LOW_RETRIEVAL_CONFIDENCE,
                EscalationSeverity.MODERATE,
                WorkflowInterruptionAction.CONTINUE_WITH_QUALIFICATION,
                "Retrieval confidence is below policy threshold.",
                thresholds.retrieval_confidence_minimum,
                signals.retrieval_confidence,
            )
        )
    if (
        signals.grounding_confidence is not None
        and signals.grounding_confidence < thresholds.grounding_confidence_minimum
    ):
        events.append(
            event(
                request,
                EscalationTriggerType.LOW_GROUNDING_CONFIDENCE,
                EscalationSeverity.HIGH,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Evidence grounding confidence is below policy threshold.",
                thresholds.grounding_confidence_minimum,
                signals.grounding_confidence,
            )
        )
    if (
        signals.verification_confidence is not None
        and signals.verification_confidence < thresholds.verification_confidence_minimum
    ):
        events.append(
            event(
                request,
                EscalationTriggerType.LOW_VERIFICATION_CONFIDENCE,
                EscalationSeverity.HIGH,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Evidence verification confidence is below policy threshold.",
                thresholds.verification_confidence_minimum,
                signals.verification_confidence,
            )
        )
    return events


def uncertainty_events(
    request: EscalationRequest,
    signals: EscalationSignals,
    thresholds: EscalationThresholds,
) -> list[EscalationEvent]:
    if signals.uncertainty_score is None:
        return []
    if signals.uncertainty_score >= thresholds.uncertainty_block:
        return [
            event(
                request,
                EscalationTriggerType.HIGH_UNCERTAINTY,
                EscalationSeverity.CRITICAL,
                WorkflowInterruptionAction.BLOCK_OUTPUT,
                "Uncertainty exceeds blocking threshold.",
                thresholds.uncertainty_block,
                signals.uncertainty_score,
            )
        ]
    if signals.uncertainty_score >= thresholds.uncertainty_human_review:
        return [
            event(
                request,
                EscalationTriggerType.HIGH_UNCERTAINTY,
                EscalationSeverity.HIGH,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Uncertainty exceeds human-review threshold.",
                thresholds.uncertainty_human_review,
                signals.uncertainty_score,
            )
        ]
    return []


def context_events(
    request: EscalationRequest,
    signals: EscalationSignals,
    thresholds: EscalationThresholds,
) -> list[EscalationEvent]:
    events: list[EscalationEvent] = []
    if (
        len(signals.missing_required_modalities)
        >= thresholds.max_missing_required_modalities_before_review
    ):
        events.append(
            event(
                request,
                EscalationTriggerType.MISSING_MODALITY,
                EscalationSeverity.MODERATE,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Required patient context modalities are missing.",
                thresholds.max_missing_required_modalities_before_review,
                len(signals.missing_required_modalities),
                modality_refs=signals.missing_required_modalities,
            )
        )
    if signals.unstable_temporal_trend_count >= thresholds.max_unstable_trends_before_review:
        events.append(
            event(
                request,
                EscalationTriggerType.UNSTABLE_TEMPORAL_TREND,
                EscalationSeverity.MODERATE,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Unstable temporal trend count exceeds policy threshold.",
                thresholds.max_unstable_trends_before_review,
                signals.unstable_temporal_trend_count,
            )
        )
    if signals.unsupported_claim_count >= thresholds.max_unsupported_claims_before_review:
        events.append(
            event(
                request,
                EscalationTriggerType.UNSUPPORTED_CLAIM,
                EscalationSeverity.HIGH,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Unsupported claim count exceeds policy threshold.",
                thresholds.max_unsupported_claims_before_review,
                signals.unsupported_claim_count,
            )
        )
    if signals.workflow_failure_count:
        events.append(
            event(
                request,
                EscalationTriggerType.WORKFLOW_FAILURE,
                EscalationSeverity.HIGH,
                WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
                "Workflow failures occurred before the safety checkpoint.",
                0,
                signals.workflow_failure_count,
            )
        )
    return events


def upstream_recommendation_events(request: EscalationRequest) -> list[EscalationEvent]:
    events: list[EscalationEvent] = []
    for recommendation in request.signals.upstream_recommendations:
        if recommendation == EscalationRecommendation.BLOCK:
            action = WorkflowInterruptionAction.BLOCK_OUTPUT
            severity = EscalationSeverity.CRITICAL
            message = "Upstream safety component recommended blocking."
        elif recommendation == EscalationRecommendation.HUMAN_REVIEW:
            action = WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW
            severity = EscalationSeverity.HIGH
            message = "Upstream safety component requested human review."
        else:
            continue
        events.append(
            event(
                request,
                EscalationTriggerType.HIGH_UNCERTAINTY,
                severity,
                action,
                message,
                None,
                recommendation.value,
            )
        )
    return events


def event(
    request: EscalationRequest,
    trigger_type: EscalationTriggerType,
    severity: EscalationSeverity,
    action: WorkflowInterruptionAction,
    message: str,
    threshold: float | int | None,
    observed_value: float | int | str | None,
    *,
    modality_refs: list[str] | None = None,
) -> EscalationEvent:
    review_actions = {
        WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
        WorkflowInterruptionAction.BLOCK_OUTPUT,
    }
    return EscalationEvent(
        event_id=f"escalation-event-{uuid4()}",
        trigger_type=trigger_type,
        severity=severity,
        action=action,
        message=message,
        threshold=threshold,
        observed_value=observed_value,
        modality_refs=modality_refs or [],
        requires_human_review=action in review_actions,
        review_queue=request.policy.review_queue,
        policy_id=request.policy.policy_id,
    )


def interruption_decision(events: list[EscalationEvent]) -> WorkflowInterruptionDecision:
    if any(item.action == WorkflowInterruptionAction.BLOCK_OUTPUT for item in events):
        return WorkflowInterruptionDecision(
            action=WorkflowInterruptionAction.BLOCK_OUTPUT,
            should_interrupt=True,
            allow_downstream_output=False,
            requires_human_review=True,
            qualification_required=True,
            reason="One or more escalation events require blocking downstream output.",
        )
    if any(item.action == WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW for item in events):
        return WorkflowInterruptionDecision(
            action=WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW,
            should_interrupt=True,
            allow_downstream_output=False,
            requires_human_review=True,
            qualification_required=True,
            reason="One or more escalation events require human review before continuation.",
        )
    if any(
        item.action == WorkflowInterruptionAction.CONTINUE_WITH_QUALIFICATION
        for item in events
    ):
        return WorkflowInterruptionDecision(
            action=WorkflowInterruptionAction.CONTINUE_WITH_QUALIFICATION,
            should_interrupt=False,
            allow_downstream_output=True,
            requires_human_review=False,
            qualification_required=True,
            reason="Workflow may continue with explicit reliability qualification.",
        )
    return WorkflowInterruptionDecision(
        action=WorkflowInterruptionAction.CONTINUE,
        should_interrupt=False,
        allow_downstream_output=True,
        requires_human_review=False,
        qualification_required=False,
        reason="No policy threshold was violated.",
    )


def recommendation_from_action(action: WorkflowInterruptionAction) -> EscalationRecommendation:
    if action == WorkflowInterruptionAction.BLOCK_OUTPUT:
        return EscalationRecommendation.BLOCK
    if action == WorkflowInterruptionAction.PAUSE_FOR_HUMAN_REVIEW:
        return EscalationRecommendation.HUMAN_REVIEW
    if action == WorkflowInterruptionAction.CONTINUE_WITH_QUALIFICATION:
        return EscalationRecommendation.QUALIFY
    return EscalationRecommendation.ALLOW


def human_review_request(
    request: EscalationRequest,
    events: list[EscalationEvent],
    interruption: WorkflowInterruptionDecision,
) -> HumanReviewRequest | None:
    if not interruption.requires_human_review:
        return None
    return HumanReviewRequest(
        review_id=f"human-review-{uuid4()}",
        queue=request.policy.review_queue,
        priority=max_severity(events),
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        reason=interruption.reason,
        blocking=not interruption.allow_downstream_output,
        event_ids=[item.event_id for item in events],
        metadata={
            "checkpoint_id": request.checkpoint_id,
            "policy_id": request.policy.policy_id,
            "policy_version": request.policy.version,
        },
    )


def max_severity(events: list[EscalationEvent]) -> EscalationSeverity:
    order = {
        EscalationSeverity.INFO: 0,
        EscalationSeverity.LOW: 1,
        EscalationSeverity.MODERATE: 2,
        EscalationSeverity.HIGH: 3,
        EscalationSeverity.CRITICAL: 4,
    }
    if not events:
        return EscalationSeverity.INFO
    return max((item.severity for item in events), key=lambda severity: order[severity])


def audit_metadata(
    request: EscalationRequest,
    events: list[EscalationEvent],
    interruption: WorkflowInterruptionDecision,
) -> dict[str, Any]:
    return {
        "case_id": request.case_id,
        "workflow_id": request.workflow_id,
        "trace_id": request.trace_id,
        "checkpoint_id": request.checkpoint_id,
        "policy_id": request.policy.policy_id,
        "policy_version": request.policy.version,
        "event_count": len(events),
        "trigger_types": sorted({item.trigger_type.value for item in events}),
        "final_action": interruption.action.value,
        "review_queue": request.policy.review_queue,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def observability_payload(
    request: EscalationRequest,
    events: list[EscalationEvent],
    interruption: WorkflowInterruptionDecision,
) -> dict[str, Any]:
    return {
        "case_id": request.case_id,
        "workflow_id": request.workflow_id,
        "trace_id": request.trace_id,
        "checkpoint_id": request.checkpoint_id,
        "policy_id": request.policy.policy_id,
        "policy_version": request.policy.version,
        "event_count": len(events),
        "critical_event_count": count_severity(events, EscalationSeverity.CRITICAL),
        "high_event_count": count_severity(events, EscalationSeverity.HIGH),
        "recommended_action": interruption.action.value,
        "should_interrupt": interruption.should_interrupt,
        "requires_human_review": interruption.requires_human_review,
        "qualification_required": interruption.qualification_required,
        "trigger_types": sorted({item.trigger_type.value for item in events}),
    }


def count_severity(events: list[EscalationEvent], severity: EscalationSeverity) -> int:
    return sum(1 for item in events if item.severity == severity)


def disabled_policy_decision(request: EscalationRequest) -> EscalationDecision:
    interruption = WorkflowInterruptionDecision(
        action=WorkflowInterruptionAction.CONTINUE,
        should_interrupt=False,
        allow_downstream_output=True,
        requires_human_review=False,
        qualification_required=False,
        reason="Escalation policy is disabled.",
    )
    return EscalationDecision(
        decision_id=f"escalation-decision-{uuid4()}",
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        checkpoint_id=request.checkpoint_id,
        policy_id=request.policy.policy_id,
        policy_version=request.policy.version,
        recommended_action=EscalationRecommendation.ALLOW,
        interruption=interruption,
        audit_metadata=audit_metadata(request, [], interruption),
        observability=observability_payload(request, [], interruption),
    )
