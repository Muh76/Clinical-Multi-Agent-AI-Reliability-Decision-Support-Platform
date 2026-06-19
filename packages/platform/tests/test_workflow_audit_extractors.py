from __future__ import annotations

from clinical_ai_platform.audit.events import WorkflowAuditEventType
from clinical_ai_platform.audit.extractors import (
    approval_audit_details,
    escalation_audit_details,
    retrieval_failed_audit_details,
    safety_blocked_audit_details,
)
from clinical_ai_platform.audit.schemas import WorkflowAuditEvent, WorkflowAuditLinkage


def _sample_response() -> dict[str, object]:
    return {
        "workflow_id": "workflow-abc",
        "status": "completed",
        "case_id": "case-1",
        "patient_id": "patient-1",
        "orchestration_status": "completed",
        "safety_status": "requires_review",
        "escalation_indicators": [
            {
                "code": "human_review",
                "level": "warning",
                "message": "Review recommended",
                "source": "escalation_logic",
            }
        ],
        "approval_requirements": {"required": True, "blocking": False, "state": "pending_review"},
        "workflow_trace_ids": {"approval_id": "approval-1", "trace_id": "trace-xyz"},
        "safety_metadata": {
            "escalation": {"recommended_action": "human_review", "events": []},
            "human_approval": {"state": "pending_review"},
        },
        "safety_events": [],
        "retrieval_metadata": {"candidate_count": 2, "retrieved_count": 1},
        "evidence": [{"rank": 1, "source_id": "src-1"}],
        "trace": {
            "trace_id": "trace-xyz",
            "steps": [
                {"name": "evidence_retrieval", "status": "completed"},
            ],
        },
        "failure_recovery": {},
    }


def test_escalation_audit_details_detects_indicators() -> None:
    detail = escalation_audit_details(_sample_response())
    assert detail is not None
    assert detail["escalation_indicator_count"] == 1


def test_approval_audit_details_detects_required_approval() -> None:
    detail = approval_audit_details(_sample_response())
    assert detail is not None
    assert detail["required"] is True
    assert detail["approval_id"] == "approval-1"


def test_safety_blocked_audit_details_returns_none_when_not_blocked() -> None:
    assert safety_blocked_audit_details(_sample_response()) is None


def test_safety_blocked_audit_details_detects_blocked_status() -> None:
    response = {**_sample_response(), "safety_status": "blocked"}
    detail = safety_blocked_audit_details(response)
    assert detail is not None
    assert detail["safety_status"] == "blocked"


def test_retrieval_failed_audit_details_detects_failed_trace_step() -> None:
    response = {
        **_sample_response(),
        "trace": {
            "trace_id": "trace-xyz",
            "steps": [{"name": "evidence_retrieval", "status": "failed", "error": "timeout"}],
        },
    }
    detail = retrieval_failed_audit_details(response)
    assert detail is not None
    assert detail["source"] == "workflow_trace"


def test_workflow_audit_event_schema_is_immutable_envelope() -> None:
    event = WorkflowAuditEvent(
        event_type=WorkflowAuditEventType.WORKFLOW_STARTED,
        linkage=WorkflowAuditLinkage(
            external_case_id="case-1",
            request_id="req-1",
        ),
        detail={"retrieval_mode": "local_corpus"},
    )
    payload = event.model_dump(mode="json")
    assert payload["schema_version"] == "workflow-audit/v1"
    assert payload["event_type"] == "workflow.started"
    assert payload["linkage"]["external_case_id"] == "case-1"
