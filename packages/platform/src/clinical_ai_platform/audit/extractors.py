from __future__ import annotations

from typing import Any


def escalation_audit_details(response: dict[str, Any]) -> dict[str, object] | None:
    indicators = response.get("escalation_indicators", [])
    if not isinstance(indicators, list):
        indicators = []
    safety = response.get("safety_metadata", {})
    if not isinstance(safety, dict):
        safety = {}
    escalation = safety.get("escalation", {})
    if not isinstance(escalation, dict):
        escalation = {}

    recommended_action = escalation.get("recommended_action")
    if not indicators and recommended_action not in {"human_review", "block", "qualify"}:
        return None

    return {
        "escalation_indicator_count": len(indicators),
        "escalation_indicators": indicators,
        "recommended_action": recommended_action,
        "escalation_events": escalation.get("events", []),
    }


def approval_audit_details(response: dict[str, Any]) -> dict[str, object] | None:
    approval = response.get("approval_requirements", {})
    if not isinstance(approval, dict):
        approval = {}
    if not approval.get("required"):
        return None
    workflow_trace_ids = response.get("workflow_trace_ids", {})
    if not isinstance(workflow_trace_ids, dict):
        workflow_trace_ids = {}
    safety = response.get("safety_metadata", {})
    human_approval = safety.get("human_approval", {}) if isinstance(safety, dict) else {}

    return {
        "required": True,
        "blocking": approval.get("blocking"),
        "state": approval.get("state"),
        "allow_workflow_resume": approval.get("allow_workflow_resume"),
        "allow_output_release": approval.get("allow_output_release"),
        "approval_id": workflow_trace_ids.get("approval_id"),
        "human_approval": human_approval,
    }


def safety_blocked_audit_details(response: dict[str, Any]) -> dict[str, object] | None:
    safety_status = str(response.get("safety_status", ""))
    if safety_status != "blocked":
        return None
    safety = response.get("safety_metadata", {})
    if not isinstance(safety, dict):
        safety = {}
    return {
        "safety_status": safety_status,
        "orchestration_status": response.get("orchestration_status"),
        "escalation": safety.get("escalation", {}),
        "failure_recovery": response.get("failure_recovery", {}),
    }


def retrieval_failed_audit_details(response: dict[str, Any]) -> dict[str, object] | None:
    trace = response.get("trace", {})
    if not isinstance(trace, dict):
        trace = {}
    steps = trace.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    failed_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("name") == "evidence_retrieval"
        and step.get("status") == "failed"
    ]
    if failed_steps:
        return {
            "source": "workflow_trace",
            "failed_steps": failed_steps,
        }

    safety_events = response.get("safety_events", [])
    if isinstance(safety_events, list):
        retrieval_events = [
            event
            for event in safety_events
            if isinstance(event, dict)
            and "retrieval" in str(event.get("event_type", "")).lower()
            and event.get("status") in {"failed", "error"}
        ]
        if retrieval_events:
            return {
                "source": "safety_events",
                "events": retrieval_events,
            }

    retrieval = response.get("retrieval_metadata", {})
    if isinstance(retrieval, dict) and retrieval.get("retrieval_failed") is True:
        return {
            "source": "retrieval_metadata",
            "retrieval_metadata": retrieval,
        }

    evidence = response.get("evidence", [])
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    retrieved_count = retrieval.get("retrieved_count", evidence_count) if isinstance(retrieval, dict) else evidence_count
    candidate_count = retrieval.get("candidate_count", 0) if isinstance(retrieval, dict) else 0
    if candidate_count > 0 and retrieved_count == 0 and evidence_count == 0:
        return {
            "source": "empty_retrieval",
            "candidate_count": candidate_count,
            "retrieved_count": retrieved_count,
            "retrieval_metadata": retrieval,
        }

    return None


def linkage_from_response(
    response: dict[str, Any],
    *,
    request_id: str | None,
    correlation_id: str | None,
    clinical_case_id: str | None = None,
    workflow_execution_id: str | None = None,
) -> dict[str, str | None]:
    trace = response.get("trace", {})
    if not isinstance(trace, dict):
        trace = {}
    workflow_trace_ids = response.get("workflow_trace_ids", {})
    if not isinstance(workflow_trace_ids, dict):
        workflow_trace_ids = {}

    return {
        "external_case_id": str(response.get("case_id", "")),
        "external_patient_id": str(response.get("patient_id", "")),
        "workflow_id": str(response.get("workflow_id", "")),
        "trace_id": str(trace.get("trace_id", workflow_trace_ids.get("trace_id", ""))),
        "output_id": _optional_str(workflow_trace_ids.get("output_id")),
        "approval_id": _optional_str(workflow_trace_ids.get("approval_id")),
        "request_id": request_id,
        "correlation_id": correlation_id,
        "clinical_case_id": clinical_case_id,
        "workflow_execution_id": workflow_execution_id,
    }


def linkage_from_request(
    request: dict[str, Any],
    *,
    request_id: str | None,
    correlation_id: str | None,
    clinical_case_id: str | None = None,
    workflow_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str | None]:
    patient_context = request.get("patient_context", {})
    if not isinstance(patient_context, dict):
        patient_context = {}
    return {
        "external_case_id": str(request.get("case_id", "")),
        "external_patient_id": _optional_str(patient_context.get("patient_id")),
        "workflow_id": workflow_id,
        "trace_id": trace_id,
        "output_id": None,
        "approval_id": None,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "clinical_case_id": clinical_case_id,
        "workflow_execution_id": None,
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
