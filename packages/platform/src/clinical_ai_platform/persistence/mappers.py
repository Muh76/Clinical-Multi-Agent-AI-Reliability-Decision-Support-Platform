from __future__ import annotations

from decimal import Decimal
from typing import Any


def evidence_metadata_from_response(response: dict[str, Any]) -> dict[str, object]:
    retrieval = response.get("retrieval_metadata", {})
    if not isinstance(retrieval, dict):
        retrieval = {}
    evidence_items = response.get("evidence", [])
    if not isinstance(evidence_items, list):
        evidence_items = []
    citations = response.get("citations", [])
    if not isinstance(citations, list):
        citations = []

    return {
        "retrieval_metadata": retrieval,
        "evidence_count": len(evidence_items),
        "citation_count": len(citations),
        "evidence_items": [
            {
                "rank": item.get("rank"),
                "source_id": item.get("source_id"),
                "source_type": item.get("source_type"),
                "citation_id": (
                    item.get("citation", {}).get("citation_id")
                    if isinstance(item.get("citation"), dict)
                    else None
                ),
                "score": item.get("score"),
                "confidence_score": item.get("confidence_score"),
                "retrieval_score": item.get("retrieval_score"),
                "rerank_score": item.get("rerank_score"),
                "source_reliability_score": item.get("source_reliability_score"),
                "metadata": item.get("metadata", {}),
            }
            for item in evidence_items
            if isinstance(item, dict)
        ],
        "citations": [
            {
                "citation_id": item.get("citation_id"),
                "source_id": item.get("source_id"),
                "source_type": item.get("source_type"),
                "title": item.get("title"),
            }
            for item in citations
            if isinstance(item, dict)
        ],
    }


def risk_metadata_from_response(response: dict[str, Any]) -> dict[str, object]:
    risk_analysis = response.get("risk_analysis", {})
    if not isinstance(risk_analysis, dict):
        risk_analysis = {}
    contributing_factors = risk_analysis.get("contributing_factors", [])
    if not isinstance(contributing_factors, list):
        contributing_factors = []
    escalation_indicators = response.get("escalation_indicators", [])
    if not isinstance(escalation_indicators, list):
        escalation_indicators = []

    return {
        "risk_level": risk_analysis.get("risk_level"),
        "risk_score": risk_analysis.get("risk_score"),
        "contributing_factor_count": len(contributing_factors),
        "contributing_factors": contributing_factors[:10],
        "escalation_indicator_count": len(escalation_indicators),
        "confidence_scores": response.get("confidence_scores", {}),
        "summary": risk_analysis.get("summary"),
    }


def safety_metadata_from_response(response: dict[str, Any]) -> dict[str, object]:
    safety = response.get("safety_metadata", {})
    if not isinstance(safety, dict):
        safety = {}
    safety_events = response.get("safety_events", [])
    if not isinstance(safety_events, list):
        safety_events = []
    approval = response.get("approval_requirements", {})
    if not isinstance(approval, dict):
        approval = {}

    return {
        "safety_status": response.get("safety_status"),
        "orchestration_status": response.get("orchestration_status"),
        "safety_metadata": safety,
        "safety_event_count": len(safety_events),
        "safety_events": safety_events,
        "approval_requirements": approval,
        "workflow_trace_ids": response.get("workflow_trace_ids", {}),
    }


def escalation_metadata_from_response(response: dict[str, Any]) -> dict[str, object]:
    indicators = response.get("escalation_indicators", [])
    if not isinstance(indicators, list):
        indicators = []
    safety = response.get("safety_metadata", {})
    if not isinstance(safety, dict):
        safety = {}
    escalation = safety.get("escalation", {})
    if not isinstance(escalation, dict):
        escalation = {}

    return {
        "escalation_indicators": indicators,
        "escalation_decision": escalation,
        "human_approval": safety.get("human_approval", {}),
        "failure_recovery": response.get("failure_recovery", {}),
    }


def evidence_snapshot_from_response(response: dict[str, Any]) -> dict[str, object]:
    return {
        "workflow_id": response.get("workflow_id"),
        "trace_id": response.get("trace", {}).get("trace_id")
        if isinstance(response.get("trace"), dict)
        else None,
        "evidence": evidence_metadata_from_response(response),
        "generated_at": response.get("generated_at"),
    }


def patient_context_metadata_from_request(request: dict[str, Any]) -> dict[str, object]:
    patient_context = request.get("patient_context", {})
    if not isinstance(patient_context, dict):
        patient_context = {}
    return {
        "patient_id": patient_context.get("patient_id"),
        "case_id": request.get("case_id"),
        "vitals_count": len(patient_context.get("vitals", []))
        if isinstance(patient_context.get("vitals"), list)
        else 0,
        "labs_count": len(patient_context.get("labs", []))
        if isinstance(patient_context.get("labs"), list)
        else 0,
        "medications_count": len(patient_context.get("medications", []))
        if isinstance(patient_context.get("medications"), list)
        else 0,
        "evidence_corpus_count": len(request.get("evidence_corpus", []))
        if isinstance(request.get("evidence_corpus"), list)
        else 0,
        "metadata": request.get("metadata", {}),
    }


def workflow_execution_record_from_response(
    *,
    response: dict[str, Any],
    retrieval_mode: str,
    request_id: str | None,
    correlation_id: str | None,
) -> dict[str, Any]:
    trace = response.get("trace", {})
    if not isinstance(trace, dict):
        trace = {}
    workflow_trace_ids = response.get("workflow_trace_ids", {})
    if not isinstance(workflow_trace_ids, dict):
        workflow_trace_ids = {}
    confidence = response.get("confidence_scores", {})
    workflow_confidence = confidence.get("workflow", 0.0) if isinstance(confidence, dict) else 0.0

    return {
        "workflow_id": str(response["workflow_id"]),
        "trace_id": str(trace.get("trace_id", response.get("workflow_id"))),
        "output_id": workflow_trace_ids.get("output_id"),
        "approval_id": workflow_trace_ids.get("approval_id"),
        "request_id": request_id,
        "correlation_id": correlation_id,
        "external_case_id": str(response["case_id"]),
        "external_patient_id": str(response["patient_id"]),
        "context_id": str(response["context_id"]),
        "status": str(response["status"]),
        "orchestration_status": str(response["orchestration_status"]),
        "safety_status": str(response["safety_status"]),
        "retrieval_mode": retrieval_mode,
        "confidence_score": Decimal(str(workflow_confidence)),
        "evidence_metadata": evidence_metadata_from_response(response),
        "risk_metadata": risk_metadata_from_response(response),
        "safety_metadata": safety_metadata_from_response(response),
        "escalation_metadata": escalation_metadata_from_response(response),
        "started_at": trace.get("started_at"),
        "completed_at": trace.get("completed_at") or response.get("generated_at"),
        "latency_ms": Decimal(str(trace.get("latency_ms", 0.0))),
    }
