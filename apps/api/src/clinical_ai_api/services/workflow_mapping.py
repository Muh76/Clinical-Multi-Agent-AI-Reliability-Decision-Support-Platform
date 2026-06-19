from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from clinical_ai_agents import SafetyAwareWorkflowOutput, SafetyAwareWorkflowRequest
from clinical_ai_api.core.agent_container import (
    ORCHESTRATED_AGENT_EXECUTION_ORDER,
    SAFETY_AWARE_WORKFLOW_EXECUTION_ORDER,
)
from clinical_ai_api.schemas.workflows import (
    AgentConfidenceScore,
    ApprovalRequirementsResponse,
    ConfidenceScoresResponse,
    EscalationIndicatorResponse,
    EvidenceCitationResponse,
    GroundedEvidenceWorkflowRequest,
    GroundedEvidenceWorkflowResponse,
    RetrievedEvidenceResponse,
    RetrievalMetadataResponse,
    SafetyAwareStatus,
    SafetyCriticIntegrationPoint,
    SafetyMetadataResponse,
    WorkflowStatus,
    WorkflowStepStatus,
    WorkflowTrace,
    WorkflowTraceIdsResponse,
    WorkflowTraceStep,
)

SAFETY_TRACE_STEPS: tuple[tuple[str, str], ...] = (
    ("hallucination_detection", "hallucination_risk"),
    ("evidence_verification", "evidence_verification"),
    ("uncertainty_scoring", "uncertainty"),
    ("escalation_logic", "escalation"),
    ("human_approval_evaluation", "approval"),
)


def to_safety_aware_request(payload: GroundedEvidenceWorkflowRequest) -> SafetyAwareWorkflowRequest:
    metadata = dict(payload.metadata)
    if payload.metadata.get("source") is None:
        metadata.setdefault("source", "request_payload")
    return SafetyAwareWorkflowRequest(
        case_id=payload.case_id,
        patient_context=payload.patient_context.model_dump(mode="json"),
        evidence_query=payload.evidence_query,
        evidence_corpus=[item.model_dump(mode="json") for item in payload.evidence_corpus],
        top_k=payload.top_k,
        candidate_limit=max(payload.top_k * 4, payload.top_k),
        rerank=payload.enable_reranking,
        metadata=metadata,
        require_human_approval_checkpoint=payload.require_human_approval_checkpoint,
    )


def from_safety_aware_output(
    *,
    payload: GroundedEvidenceWorkflowRequest,
    output: SafetyAwareWorkflowOutput,
    request_id: str | None,
    correlation_id: str | None,
    retrieval_mode: str,
) -> GroundedEvidenceWorkflowResponse:
    base = output.base_workflow
    structured_context = base.structured_patient_context
    patient_id = str(structured_context.get("patient_id", payload.patient_context.patient_id))
    context_id = str(structured_context.get("context_id", patient_id))
    retrieval_query = str(payload.evidence_query or _retrieval_query_from_output(base) or "")
    validation_findings = structured_context.get("validation_findings", [])
    if not isinstance(validation_findings, list):
        validation_findings = []

    evidence = [_map_evidence_item(item) for item in base.retrieved_evidence if isinstance(item, dict)]
    citations = [_map_citation_item(item) for item in base.citations if isinstance(item, dict)]
    confidence_score = _workflow_confidence(base.confidence_scores)
    safety_review_recommended = bool(
        output.approval_requirements.get("required")
        or output.base_workflow.workflow_trace.get("human_review_required")
        or output.status in {"requires_review", "blocked", "qualified"}
    )

    trace = _build_workflow_trace(
        output=output,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    return GroundedEvidenceWorkflowResponse(
        workflow_id=output.workflow_id,
        status=_api_workflow_status(output),
        case_id=output.case_id,
        patient_id=patient_id,
        context_id=context_id,
        evidence=evidence,
        citations=citations,
        confidence_score=confidence_score,
        retrieval_metadata=RetrievalMetadataResponse(
            query=retrieval_query,
            retrieval_mode=_retrieval_mode_label(base, retrieval_mode),
            candidate_count=_candidate_count(payload, base),
            retrieved_count=len(evidence),
            reranked=bool(base.explainability.get("reranked"))
            if isinstance(base.explainability, dict)
            else bool(payload.enable_reranking),
            top_k=payload.top_k,
            context_id=context_id,
            patient_id=patient_id,
            validation_finding_count=len(validation_findings),
            safety_review_recommended=safety_review_recommended,
        ),
        trace=trace,
        safety_critic_integration_points=_safety_critic_integration_points(output),
        orchestration_status=str(base.status),
        agent_execution_order=list(ORCHESTRATED_AGENT_EXECUTION_ORDER),
        risk_analysis=output.risk_analysis if isinstance(output.risk_analysis, dict) else {},
        safety_status=_safety_aware_status(output.status),
        workflow_execution_order=list(SAFETY_AWARE_WORKFLOW_EXECUTION_ORDER),
        confidence_scores=_map_confidence_scores(output),
        safety_metadata=_map_safety_metadata(output),
        safety_events=output.safety_events,
        escalation_indicators=_map_escalation_indicators(output),
        approval_requirements=_map_approval_requirements(output),
        workflow_trace_ids=_map_workflow_trace_ids(output),
        failure_recovery=output.failure_recovery if isinstance(output.failure_recovery, dict) else {},
        generated_at=output.generated_at,
    )


def _api_workflow_status(output: SafetyAwareWorkflowOutput) -> WorkflowStatus:
    if output.status == "failed" or output.base_workflow.status == "failed":
        return WorkflowStatus.FAILED
    return WorkflowStatus.COMPLETED


def _safety_aware_status(status: str) -> SafetyAwareStatus:
    try:
        return SafetyAwareStatus(status)
    except ValueError:
        return SafetyAwareStatus.COMPLETED


def _workflow_confidence(confidence_scores: dict[str, Any]) -> float:
    value = confidence_scores.get("workflow")
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def _map_confidence_scores(output: SafetyAwareWorkflowOutput) -> ConfidenceScoresResponse:
    base_scores = output.base_workflow.confidence_scores
    agents: dict[str, AgentConfidenceScore] = {}
    raw_agents = base_scores.get("agents", {})
    if isinstance(raw_agents, dict):
        for node_id, agent_score in raw_agents.items():
            if not isinstance(agent_score, dict):
                continue
            score = agent_score.get("score")
            if isinstance(score, int | float):
                agents[str(node_id)] = AgentConfidenceScore(
                    score=max(0.0, min(1.0, float(score))),
                    band=str(agent_score.get("band")) if agent_score.get("band") else None,
                )
    return ConfidenceScoresResponse(
        workflow=_workflow_confidence(base_scores),
        workflow_band=str(base_scores.get("workflow_band")) if base_scores.get("workflow_band") else None,
        agents=agents,
        hallucination_grounding=_optional_float(output.hallucination_risk.get("grounding_confidence")),
        verification=_optional_float(output.evidence_verification.get("verification_confidence")),
        uncertainty=_optional_float(output.uncertainty.get("uncertainty_score")),
    )


def _map_safety_metadata(output: SafetyAwareWorkflowOutput) -> SafetyMetadataResponse:
    return SafetyMetadataResponse(
        hallucination_detection=output.hallucination_risk if isinstance(output.hallucination_risk, dict) else {},
        evidence_verification=output.evidence_verification if isinstance(output.evidence_verification, dict) else {},
        uncertainty_scoring=output.uncertainty if isinstance(output.uncertainty, dict) else {},
        escalation=output.escalation if isinstance(output.escalation, dict) else {},
        human_approval=output.approval if isinstance(output.approval, dict) else {},
        safety_critic=output.safety_critic if isinstance(output.safety_critic, dict) else {},
    )


def _map_approval_requirements(output: SafetyAwareWorkflowOutput) -> ApprovalRequirementsResponse:
    requirements = output.approval_requirements
    return ApprovalRequirementsResponse(
        required=bool(requirements.get("required")),
        blocking=bool(requirements.get("blocking")),
        state=str(requirements["state"]) if requirements.get("state") is not None else None,
        allow_workflow_resume=requirements.get("allow_workflow_resume"),
        allow_output_release=requirements.get("allow_output_release"),
    )


def _map_workflow_trace_ids(output: SafetyAwareWorkflowOutput) -> WorkflowTraceIdsResponse:
    trace_ids = output.workflow_trace_ids
    return WorkflowTraceIdsResponse(
        workflow_id=str(trace_ids.get("workflow_id") or output.workflow_id),
        trace_id=str(trace_ids.get("trace_id") or output.trace_id),
        output_id=output.output_id,
        approval_id=str(trace_ids.get("approval_id")) if trace_ids.get("approval_id") else None,
    )


def _map_escalation_indicators(output: SafetyAwareWorkflowOutput) -> list[EscalationIndicatorResponse]:
    indicators: list[EscalationIndicatorResponse] = []
    seen: set[str] = set()

    for item in output.base_workflow.escalation_indicators:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("indicator_id") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        indicators.append(
            EscalationIndicatorResponse(
                code=code,
                level=str(item.get("level") or item.get("severity") or "unknown"),
                message=str(item.get("message") or item.get("summary") or code),
                source="risk_analysis",
            )
        )

    escalation = output.escalation if isinstance(output.escalation, dict) else {}
    for event in escalation.get("events", []):
        if not isinstance(event, dict):
            continue
        code = str(event.get("code") or event.get("event_type") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        indicators.append(
            EscalationIndicatorResponse(
                code=code,
                level=str(event.get("severity") or event.get("level") or "unknown"),
                message=str(event.get("message") or event.get("summary") or code),
                source="escalation_logic",
            )
        )
    return indicators


def _optional_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return None


def _retrieval_query_from_output(base_output: Any) -> str | None:
    explainability = base_output.explainability
    if not isinstance(explainability, dict):
        return None
    for item in explainability.get("reasoning_metadata", []):
        if isinstance(item, dict) and item.get("reasoning_id") == "evidence.retrieval":
            summary = item.get("summary", "")
            if isinstance(summary, str) and "query:" in summary.lower():
                return summary
    return None


def _candidate_count(payload: GroundedEvidenceWorkflowRequest, base_output: Any) -> int:
    if payload.evidence_corpus:
        return len(payload.evidence_corpus)
    explainability = base_output.explainability
    if isinstance(explainability, dict):
        for item in explainability.get("reasoning_metadata", []):
            if not isinstance(item, dict) or item.get("reasoning_id") != "evidence.retrieval":
                continue
            summary = str(item.get("summary", ""))
            if "candidate" in summary.lower():
                return max(len(base_output.retrieved_evidence), 0)
    return 0


def _retrieval_mode_label(base_output: Any, fallback: str) -> str:
    explainability = base_output.explainability
    if isinstance(explainability, dict):
        backend = explainability.get("retrieval_backend")
        if backend:
            return str(backend)
        structured = explainability.get("structured_payload", {})
        if isinstance(structured, dict) and structured.get("retrieval_mode"):
            return str(structured["retrieval_mode"])
    return fallback


def _map_evidence_item(item: dict[str, Any]) -> RetrievedEvidenceResponse:
    citation_id = str(item.get("citation_id") or item.get("source_id") or item.get("chunk_id"))
    scoring = item.get("scoring_components", {})
    if not isinstance(scoring, dict):
        scoring = {}
    citation = EvidenceCitationResponse(
        citation_id=citation_id,
        source_id=str(item.get("source_id", citation_id)),
        source_type=str(item.get("source_type", "unknown")),
        title=item.get("title"),
        url=item.get("url"),
        publication_year=item.get("publication_year"),
        quote=str(item.get("text", ""))[:500] or None,
        attribution_text=str(
            item.get("metadata", {}).get("citation_text")
            or item.get("relevance_reasoning")
            or citation_id
        ),
    )
    retrieval_score = float(
        scoring.get("retrieval")
        or scoring.get("bm25")
        or scoring.get("dense")
        or item.get("score", 0.0)
    )
    rerank_score = scoring.get("rerank")
    return RetrievedEvidenceResponse(
        rank=int(item.get("rank", 1)),
        source_id=str(item.get("source_id", citation_id)),
        source_type=str(item.get("source_type", "unknown")),
        text=str(item.get("text", "")),
        citation=citation,
        score=float(item.get("score", 0.0)),
        confidence_score=float(item.get("confidence_score", item.get("score", 0.0))),
        retrieval_score=retrieval_score,
        rerank_score=float(rerank_score) if isinstance(rerank_score, int | float) else None,
        source_reliability_score=float(item.get("source_reliability_score", 0.0)),
        metadata=item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
    )


def _map_citation_item(item: dict[str, Any]) -> EvidenceCitationResponse:
    citation_id = str(item.get("citation_id") or item.get("source_id"))
    return EvidenceCitationResponse(
        citation_id=citation_id,
        source_id=str(item.get("source_id", citation_id)),
        source_type=str(item.get("source_type", "unknown")),
        title=item.get("title"),
        url=item.get("url"),
        publication_year=item.get("publication_year"),
        quote=item.get("quote"),
        attribution_text=str(item.get("attribution_text") or citation_id),
    )


def _build_workflow_trace(
    *,
    output: SafetyAwareWorkflowOutput,
    request_id: str | None,
    correlation_id: str | None,
) -> WorkflowTrace:
    completed_at = output.generated_at
    trace_graph = output.base_workflow.workflow_trace
    duration_ms = float(trace_graph.get("duration_ms", 0.0)) if isinstance(trace_graph, dict) else 0.0
    started_at = completed_at - timedelta(milliseconds=duration_ms)
    steps = _trace_steps_from_output(output, started_at=started_at, completed_at=completed_at)
    return WorkflowTrace(
        workflow_id=output.workflow_id,
        trace_id=output.trace_id,
        request_id=request_id,
        correlation_id=correlation_id,
        started_at=started_at,
        completed_at=completed_at,
        latency_ms=max(0.0, duration_ms),
        steps=steps,
    )


def _trace_steps_from_output(
    output: SafetyAwareWorkflowOutput,
    *,
    started_at: datetime,
    completed_at: datetime,
) -> list[WorkflowTraceStep]:
    trace_graph = output.base_workflow.workflow_trace
    raw_nodes = trace_graph.get("nodes", []) if isinstance(trace_graph, dict) else []
    nodes_by_id = {
        str(node.get("node_id")): node
        for node in raw_nodes
        if isinstance(node, dict) and node.get("node_id")
    }

    steps: list[WorkflowTraceStep] = []
    cursor = started_at
    for node_id in ORCHESTRATED_AGENT_EXECUTION_ORDER:
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        latency_ms = float(node.get("latency_ms", 0.0))
        step_started = cursor
        step_completed = cursor + timedelta(milliseconds=latency_ms)
        cursor = step_completed
        node_status = str(node.get("status", "completed"))
        steps.append(
            WorkflowTraceStep(
                name=node_id,
                status=(
                    WorkflowStepStatus.COMPLETED
                    if node_status == "completed"
                    else WorkflowStepStatus.FAILED
                ),
                started_at=step_started,
                completed_at=step_completed,
                latency_ms=latency_ms,
                metadata={
                    "source": "AgentWorkflowOrchestrator",
                    "agent_role": str(node.get("agent_role", "")),
                    "agent_run_id": str(node.get("agent_run_id", "")),
                    "confidence_score": node.get("confidence_score"),
                },
            )
        )

    remaining_ms = max(0.0, (completed_at - cursor).total_seconds() * 1000)
    safety_step_count = len(SAFETY_TRACE_STEPS)
    per_step_ms = remaining_ms / safety_step_count if safety_step_count else 0.0
    for step_name, payload_key in SAFETY_TRACE_STEPS:
        payload = getattr(output, payload_key, {})
        if not isinstance(payload, dict):
            payload = {}
        step_started = cursor
        step_completed = cursor + timedelta(milliseconds=per_step_ms)
        cursor = step_completed
        steps.append(
            WorkflowTraceStep(
                name=step_name,
                status=WorkflowStepStatus.COMPLETED,
                started_at=step_started,
                completed_at=step_completed,
                latency_ms=per_step_ms,
                metadata={
                    "source": "SafetyAwareClinicalWorkflowRunner",
                    "status": _safety_step_status(step_name, output, payload),
                    "recommended_action": payload.get("recommended_action")
                    or payload.get("state"),
                },
            )
        )

    return steps


def _safety_step_status(step_name: str, output: SafetyAwareWorkflowOutput, payload: dict[str, Any]) -> str:
    if step_name == "human_approval_evaluation":
        return str(payload.get("state") or output.approval_requirements.get("state") or "evaluated")
    if step_name == "escalation_logic":
        return str(payload.get("recommended_action") or output.safety_critic.get("status") or "evaluated")
    return str(output.safety_critic.get("status") or payload.get("status") or "evaluated")


def _safety_critic_integration_points(
    output: SafetyAwareWorkflowOutput,
) -> list[SafetyCriticIntegrationPoint]:
    safety_status = str(output.safety_critic.get("status", "unknown"))
    integration_status = "available" if safety_status in {"passed", "requires_review", "blocked"} else "planned"
    return [
        SafetyCriticIntegrationPoint(
            name="citation_allow_list",
            status="available",
            required_inputs=["citations", "retrieved_evidence"],
        ),
        SafetyCriticIntegrationPoint(
            name="grounding_consistency_check",
            status=integration_status,
            required_inputs=["candidate_answer", "retrieved_evidence", "citations"],
        ),
        SafetyCriticIntegrationPoint(
            name="recommendation_strength_review",
            status=integration_status,
            required_inputs=["confidence_scores", "source_reliability_scores", "patient_context"],
        ),
        SafetyCriticIntegrationPoint(
            name="hallucination_detection",
            status="available",
            required_inputs=["claims", "retrieved_evidence", "citations"],
        ),
        SafetyCriticIntegrationPoint(
            name="evidence_verification",
            status="available",
            required_inputs=["claims", "evidence_references"],
        ),
        SafetyCriticIntegrationPoint(
            name="uncertainty_scoring",
            status="available",
            required_inputs=["retrieval_confidence", "verification_confidence", "risk_analysis"],
        ),
        SafetyCriticIntegrationPoint(
            name="escalation_logic",
            status="available",
            required_inputs=["hallucination_risk", "uncertainty_score", "escalation_policy"],
        ),
        SafetyCriticIntegrationPoint(
            name="human_approval_evaluation",
            status="available",
            required_inputs=["escalation_decision", "approval_checkpoint"],
        ),
    ]
