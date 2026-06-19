from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from clinical_ai_agents import SafetyAwareWorkflowOutput, SafetyAwareWorkflowRequest
from clinical_ai_api.schemas.workflows import (
    EvidenceCitationResponse,
    GroundedEvidenceWorkflowRequest,
    GroundedEvidenceWorkflowResponse,
    RetrievedEvidenceResponse,
    RetrievalMetadataResponse,
    SafetyCriticIntegrationPoint,
    WorkflowStatus,
    WorkflowStepStatus,
    WorkflowTrace,
    WorkflowTraceStep,
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
        require_human_approval_checkpoint=True,
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
            candidate_count=len(payload.evidence_corpus),
            retrieved_count=len(evidence),
            reranked=bool(payload.enable_reranking),
            top_k=payload.top_k,
            context_id=context_id,
            patient_id=patient_id,
            validation_finding_count=len(validation_findings),
            safety_review_recommended=safety_review_recommended,
        ),
        trace=trace,
        safety_critic_integration_points=_safety_critic_integration_points(output),
        generated_at=output.generated_at,
    )


def _api_workflow_status(output: SafetyAwareWorkflowOutput) -> WorkflowStatus:
    if output.status == "failed" or output.base_workflow.status == "failed":
        return WorkflowStatus.FAILED
    return WorkflowStatus.COMPLETED


def _workflow_confidence(confidence_scores: dict[str, Any]) -> float:
    value = confidence_scores.get("workflow")
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return 0.0


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


def _retrieval_mode_label(base_output: Any, fallback: str) -> str:
    explainability = base_output.explainability
    if isinstance(explainability, dict):
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
    retrieval_score = float(scoring.get("retrieval", item.get("score", 0.0)))
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
    nodes = trace_graph.get("nodes", []) if isinstance(trace_graph, dict) else []
    steps: list[WorkflowTraceStep] = []
    cursor = started_at
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        latency_ms = float(node.get("latency_ms", 0.0))
        step_started = cursor
        step_completed = cursor + timedelta(milliseconds=latency_ms)
        cursor = step_completed
        node_status = str(node.get("status", "completed"))
        steps.append(
            WorkflowTraceStep(
                name=str(node.get("node_id", f"agent_step_{index}")),
                status=(
                    WorkflowStepStatus.COMPLETED
                    if node_status == "completed"
                    else WorkflowStepStatus.FAILED
                ),
                started_at=step_started,
                completed_at=step_completed,
                latency_ms=latency_ms,
                metadata={
                    "agent_role": str(node.get("agent_role", "")),
                    "agent_run_id": str(node.get("agent_run_id", "")),
                    "confidence_score": node.get("confidence_score"),
                },
            )
        )

    safety_latency = max(
        0.0,
        (completed_at - cursor).total_seconds() * 1000 / 2,
    )
    steps.append(
        WorkflowTraceStep(
            name="safety_critic_evaluation",
            status=WorkflowStepStatus.COMPLETED,
            started_at=cursor,
            completed_at=cursor + timedelta(milliseconds=safety_latency),
            latency_ms=safety_latency,
            metadata={
                "safety_critic_status": output.safety_critic.get("status"),
                "safety_event_count": len(output.safety_events),
            },
        )
    )
    package_started = cursor + timedelta(milliseconds=safety_latency)
    steps.append(
        WorkflowTraceStep(
            name="package_grounded_evidence_response",
            status=WorkflowStepStatus.COMPLETED,
            started_at=package_started,
            completed_at=completed_at,
            latency_ms=max(0.0, (completed_at - package_started).total_seconds() * 1000),
            metadata={
                "workflow_status": output.status,
                "evidence_count": len(output.retrieved_evidence),
                "citation_count": len(output.base_workflow.citations),
            },
        )
    )
    return steps


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
    ]
