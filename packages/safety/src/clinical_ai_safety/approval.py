from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from clinical_ai_safety.escalation import (
    EscalationDecision,
    EscalationEvent,
    EscalationSeverity,
    HumanReviewRequest,
)


class ApprovalState(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUESTED = "requested"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    REJECTED = "rejected"
    MORE_INFORMATION_REQUIRED = "more_information_required"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REJECT = "reject"
    REQUEST_MORE_INFORMATION = "request_more_information"
    CANCEL = "cancel"


class ReviewCheckpointType(StrEnum):
    POST_RETRIEVAL = "post_retrieval"
    POST_RISK_ANALYSIS = "post_risk_analysis"
    POST_SAFETY_CRITIC = "post_safety_critic"
    PRE_OUTPUT_RELEASE = "pre_output_release"
    GOVERNANCE_REVIEW = "governance_review"


class ReviewerRole(StrEnum):
    CLINICIAN = "clinician"
    SAFETY_REVIEWER = "safety_reviewer"
    GOVERNANCE_REVIEWER = "governance_reviewer"
    ADMIN = "admin"


class ApprovalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewerIdentity(ApprovalModel):
    reviewer_id: str
    display_name: str | None = None
    role: ReviewerRole
    organization: str | None = None


class ReviewCheckpoint(ApprovalModel):
    checkpoint_id: str
    checkpoint_type: ReviewCheckpointType
    name: str
    required: bool = True
    blocking: bool = True
    queue: str = "clinical_safety_review"
    policy_refs: list[str] = Field(default_factory=list)


class ReviewerContextPackage(ApprovalModel):
    context_id: str
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    checkpoint: ReviewCheckpoint
    summary: str
    escalation_events: list[EscalationEvent] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    modality_refs: list[str] = Field(default_factory=list)
    confidence_summary: dict[str, float | str] = Field(default_factory=dict)
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)
    redacted_payload_refs: dict[str, str] = Field(default_factory=dict)


class ApprovalAuditEvent(ApprovalModel):
    audit_event_id: str
    approval_id: str
    event_type: str
    from_state: ApprovalState | None = None
    to_state: ApprovalState
    actor_id: str | None = None
    actor_role: ReviewerRole | None = None
    reason: str | None = None
    trace_id: str | None = None
    workflow_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApprovalDecision(ApprovalModel):
    decision_id: str
    decision_type: ApprovalDecisionType
    reviewer: ReviewerIdentity
    rationale: str
    conditions: list[str] = Field(default_factory=list)
    requested_information: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalWorkflowRequest(ApprovalModel):
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    checkpoint: ReviewCheckpoint
    escalation_decision: EscalationDecision | None = None
    human_review_request: HumanReviewRequest | None = None
    summary: str = "Human review requested for clinical AI reliability workflow."
    evidence_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    modality_refs: list[str] = Field(default_factory=list)
    confidence_summary: dict[str, float | str] = Field(default_factory=dict)
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalWorkflowRecord(ApprovalModel):
    approval_id: str
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    state: ApprovalState
    checkpoint: ReviewCheckpoint
    reviewer_context: ReviewerContextPackage
    human_review_request: HumanReviewRequest | None = None
    decisions: list[ApprovalDecision] = Field(default_factory=list)
    audit_events: list[ApprovalAuditEvent] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApprovalWorkflowOutput(ApprovalModel):
    approval_id: str
    state: ApprovalState
    allow_workflow_resume: bool
    allow_output_release: bool
    requires_follow_up: bool
    conditions: list[str] = Field(default_factory=list)
    requested_information: list[str] = Field(default_factory=list)
    audit_event_ids: list[str] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)


class HumanApprovalWorkflowEngine:
    def create_review(self, request: ApprovalWorkflowRequest) -> ApprovalWorkflowRecord:
        return create_approval_workflow(request)

    def apply_decision(
        self,
        record: ApprovalWorkflowRecord,
        decision: ApprovalDecision,
    ) -> ApprovalWorkflowRecord:
        return apply_approval_decision(record, decision)


def create_approval_workflow(request: ApprovalWorkflowRequest) -> ApprovalWorkflowRecord:
    review_required = request.human_review_request is not None or (
        request.escalation_decision is not None
        and request.escalation_decision.interruption.requires_human_review
    )
    state = ApprovalState.REQUESTED if review_required else ApprovalState.NOT_REQUIRED
    approval_id = f"approval-{uuid4()}"
    context = reviewer_context_package(request)
    initial_audit_event = audit_event(
        approval_id=approval_id,
        event_type="approval_requested" if review_required else "approval_not_required",
        from_state=None,
        to_state=state,
        trace_id=request.trace_id,
        workflow_id=request.workflow_id,
        metadata={
            "checkpoint_id": request.checkpoint.checkpoint_id,
            "checkpoint_type": request.checkpoint.checkpoint_type.value,
        },
    )
    record = ApprovalWorkflowRecord(
        approval_id=approval_id,
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        state=state,
        checkpoint=request.checkpoint,
        reviewer_context=context,
        human_review_request=request.human_review_request,
        audit_events=[initial_audit_event],
        observability=approval_observability_payload(
            approval_id=approval_id,
            state=state,
            request=request,
            event_count=1,
        ),
    )
    return record


def apply_approval_decision(
    record: ApprovalWorkflowRecord,
    decision: ApprovalDecision,
) -> ApprovalWorkflowRecord:
    next_state = next_state_for_decision(record.state, decision.decision_type)
    event = audit_event(
        approval_id=record.approval_id,
        event_type=f"approval_decision.{decision.decision_type.value}",
        from_state=record.state,
        to_state=next_state,
        actor_id=decision.reviewer.reviewer_id,
        actor_role=decision.reviewer.role,
        reason=decision.rationale,
        trace_id=record.trace_id,
        workflow_id=record.workflow_id,
        metadata={
            "decision_id": decision.decision_id,
            "condition_count": len(decision.conditions),
            "requested_information_count": len(decision.requested_information),
        },
    )
    decisions = [*record.decisions, decision]
    audit_events = [*record.audit_events, event]
    return record.model_copy(
        update={
            "state": next_state,
            "decisions": decisions,
            "audit_events": audit_events,
            "updated_at": datetime.now(UTC),
            "observability": approval_record_observability(
                record.approval_id,
                next_state,
                record,
                len(audit_events),
            ),
        }
    )


def approval_output(record: ApprovalWorkflowRecord) -> ApprovalWorkflowOutput:
    latest_decision = record.decisions[-1] if record.decisions else None
    conditions = latest_decision.conditions if latest_decision else []
    requested_information = latest_decision.requested_information if latest_decision else []
    return ApprovalWorkflowOutput(
        approval_id=record.approval_id,
        state=record.state,
        allow_workflow_resume=record.state
        in {
            ApprovalState.APPROVED,
            ApprovalState.APPROVED_WITH_CONDITIONS,
            ApprovalState.NOT_REQUIRED,
        },
        allow_output_release=record.state in {ApprovalState.APPROVED, ApprovalState.NOT_REQUIRED},
        requires_follow_up=record.state
        in {ApprovalState.APPROVED_WITH_CONDITIONS, ApprovalState.MORE_INFORMATION_REQUIRED},
        conditions=conditions,
        requested_information=requested_information,
        audit_event_ids=[event.audit_event_id for event in record.audit_events],
        observability=record.observability,
    )


def reviewer_context_package(request: ApprovalWorkflowRequest) -> ReviewerContextPackage:
    escalation_events = (
        request.escalation_decision.events if request.escalation_decision is not None else []
    )
    return ReviewerContextPackage(
        context_id=f"review-context-{uuid4()}",
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        checkpoint=request.checkpoint,
        summary=request.summary,
        escalation_events=escalation_events,
        evidence_refs=sorted(set(request.evidence_refs)),
        claim_refs=sorted(set(request.claim_refs)),
        modality_refs=sorted(set(request.modality_refs)),
        confidence_summary=request.confidence_summary,
        risk_summary=request.risk_summary,
        limitations=request.limitations,
        recommended_questions=recommended_review_questions(request, escalation_events),
        redacted_payload_refs={
            key: str(value)
            for key, value in request.metadata.items()
            if key.endswith("_ref") or key.endswith("_id")
        },
    )


def recommended_review_questions(
    request: ApprovalWorkflowRequest,
    events: list[EscalationEvent],
) -> list[str]:
    questions = [
        "Does the cited evidence support the downstream claim or risk statement?",
        "Are uncertainty and missing modality limitations clearly represented?",
    ]
    trigger_types = {event.trigger_type.value for event in events}
    if "contradictory_evidence" in trigger_types:
        questions.append("How should contradictory evidence be resolved or qualified?")
    if "hallucination_risk" in trigger_types or "unsupported_claim" in trigger_types:
        questions.append("Should unsupported claims be removed, rewritten, or blocked?")
    if request.modality_refs:
        questions.append("Are missing modalities required before this workflow can continue?")
    return questions


def next_state_for_decision(
    current_state: ApprovalState,
    decision_type: ApprovalDecisionType,
) -> ApprovalState:
    if current_state in {ApprovalState.CANCELLED, ApprovalState.EXPIRED}:
        return current_state
    return {
        ApprovalDecisionType.APPROVE: ApprovalState.APPROVED,
        ApprovalDecisionType.APPROVE_WITH_CONDITIONS: ApprovalState.APPROVED_WITH_CONDITIONS,
        ApprovalDecisionType.REJECT: ApprovalState.REJECTED,
        ApprovalDecisionType.REQUEST_MORE_INFORMATION: ApprovalState.MORE_INFORMATION_REQUIRED,
        ApprovalDecisionType.CANCEL: ApprovalState.CANCELLED,
    }[decision_type]


def audit_event(
    *,
    approval_id: str,
    event_type: str,
    from_state: ApprovalState | None,
    to_state: ApprovalState,
    actor_id: str | None = None,
    actor_role: ReviewerRole | None = None,
    reason: str | None = None,
    trace_id: str | None = None,
    workflow_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ApprovalAuditEvent:
    return ApprovalAuditEvent(
        audit_event_id=f"approval-audit-{uuid4()}",
        approval_id=approval_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        trace_id=trace_id,
        workflow_id=workflow_id,
        metadata=metadata or {},
    )


def approval_observability_payload(
    *,
    approval_id: str,
    state: ApprovalState,
    request: ApprovalWorkflowRequest,
    event_count: int,
) -> dict[str, Any]:
    return {
        "approval_id": approval_id,
        "case_id": request.case_id,
        "workflow_id": request.workflow_id,
        "trace_id": request.trace_id,
        "checkpoint_id": request.checkpoint.checkpoint_id,
        "checkpoint_type": request.checkpoint.checkpoint_type.value,
        "state": state.value,
        "queue": request.checkpoint.queue,
        "blocking": request.checkpoint.blocking,
        "event_count": event_count,
        "human_review_request_id": (
            request.human_review_request.review_id if request.human_review_request else None
        ),
    }


def approval_record_observability(
    approval_id: str,
    state: ApprovalState,
    record: ApprovalWorkflowRecord,
    event_count: int,
) -> dict[str, Any]:
    return {
        "approval_id": approval_id,
        "case_id": record.case_id,
        "workflow_id": record.workflow_id,
        "trace_id": record.trace_id,
        "checkpoint_id": record.checkpoint.checkpoint_id,
        "checkpoint_type": record.checkpoint.checkpoint_type.value,
        "state": state.value,
        "queue": record.checkpoint.queue,
        "blocking": record.checkpoint.blocking,
        "decision_count": len(record.decisions),
        "event_count": event_count,
    }
