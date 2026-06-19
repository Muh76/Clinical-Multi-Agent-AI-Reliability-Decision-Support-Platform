from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from clinical_ai_platform.audit.events import WorkflowAuditEventType
from clinical_ai_platform.audit.service import WorkflowAuditService
from clinical_ai_platform.db.models.audit_log import AuditLog


def _audit_log_stub() -> AuditLog:
    return AuditLog(
        id=uuid4(),
        event_type="workflow.started",
        actor_type="system",
        event_source="workflow_audit",
        payload={},
    )


def _sample_response() -> dict[str, object]:
    return {
        "workflow_id": "workflow-abc",
        "status": "completed",
        "case_id": "case-1",
        "patient_id": "patient-1",
        "context_id": "ctx-1",
        "orchestration_status": "completed",
        "safety_status": "requires_review",
        "confidence_scores": {"workflow": 0.82},
        "escalation_indicators": [
            {
                "code": "human_review",
                "level": "warning",
                "message": "Review recommended",
                "source": "escalation_logic",
            }
        ],
        "approval_requirements": {"required": True, "blocking": False, "state": "pending_review"},
        "workflow_trace_ids": {
            "approval_id": "approval-1",
            "trace_id": "trace-xyz",
            "output_id": "output-1",
        },
        "safety_metadata": {
            "escalation": {"recommended_action": "human_review", "events": []},
            "human_approval": {"state": "pending_review"},
        },
        "safety_events": [],
        "retrieval_metadata": {"candidate_count": 2, "retrieved_count": 1},
        "evidence": [{"rank": 1, "source_id": "src-1"}],
        "trace": {
            "trace_id": "trace-xyz",
            "latency_ms": 100.0,
            "steps": [{"name": "evidence_retrieval", "status": "completed"}],
        },
        "failure_recovery": {},
    }


@pytest.mark.asyncio
async def test_record_started_appends_workflow_started_event() -> None:
    audit_repo = AsyncMock()
    audit_repo.append_many.return_value = [_audit_log_stub()]
    service = WorkflowAuditService(audit_repo)
    case_id = uuid4()

    await service.record_started(
        request_payload={
            "case_id": "case-1",
            "patient_context": {"patient_id": "patient-1"},
            "top_k": 5,
        },
        retrieval_mode="local_corpus",
        request_id="req-1",
        correlation_id="corr-1",
        clinical_case_id=case_id,
    )

    audit_repo.append_many.assert_awaited_once()
    record = audit_repo.append_many.await_args.args[0][0]
    assert record.event_type == WorkflowAuditEventType.WORKFLOW_STARTED
    assert record.clinical_case_id == case_id
    assert record.linkage.request_id == "req-1"


@pytest.mark.asyncio
async def test_record_outcome_events_appends_escalation_and_approval() -> None:
    audit_repo = AsyncMock()
    audit_repo.append_many.return_value = [_audit_log_stub()]
    service = WorkflowAuditService(audit_repo)
    case_id = uuid4()
    execution_id = uuid4()

    await service.record_outcome_events(
        response_payload=_sample_response(),
        request_id="req-1",
        correlation_id="corr-1",
        clinical_case_id=case_id,
        workflow_execution_id=execution_id,
    )

    audit_repo.append_many.assert_awaited_once()
    records = audit_repo.append_many.await_args.args[0]
    event_types = {record.event_type for record in records}
    assert WorkflowAuditEventType.ESCALATION_TRIGGERED in event_types
    assert WorkflowAuditEventType.APPROVAL_REQUIRED in event_types
    assert all(record.workflow_execution_id == execution_id for record in records)


@pytest.mark.asyncio
async def test_record_failed_includes_trace_linkage_when_response_present() -> None:
    audit_repo = AsyncMock()
    audit_repo.append_many.return_value = [_audit_log_stub()]
    service = WorkflowAuditService(audit_repo)
    case_id = uuid4()

    await service.record_failed(
        request_payload={"case_id": "case-1", "patient_context": {"patient_id": "patient-1"}},
        request_id="req-1",
        correlation_id="corr-1",
        error_code="clinical_reliability_workflow_failed",
        error_message="failed",
        clinical_case_id=case_id,
        response_payload=_sample_response(),
    )

    record = audit_repo.append_many.await_args.args[0][0]
    assert record.event_type == WorkflowAuditEventType.WORKFLOW_FAILED
    assert record.linkage.workflow_id == "workflow-abc"
    assert record.linkage.trace_id == "trace-xyz"
