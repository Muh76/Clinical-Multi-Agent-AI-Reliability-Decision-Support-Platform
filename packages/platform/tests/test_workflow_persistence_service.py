from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from clinical_ai_platform.audit.service import WorkflowAuditService
from clinical_ai_platform.db.models.clinical_case import ClinicalCase
from clinical_ai_platform.db.models.workflow_execution import WorkflowExecution
from clinical_ai_platform.persistence.workflow_persistence import WorkflowPersistenceService


@pytest.mark.asyncio
async def test_persist_completed_run_writes_case_execution_and_audit_events() -> None:
    case_id = uuid4()
    execution_id = uuid4()

    clinical_case = ClinicalCase(
        id=case_id,
        external_case_id="case-1",
        patient_id=uuid4(),
        title="Case case-1",
        status="open",
        safety_status="requires_review",
        evidence_snapshot={},
    )
    workflow_execution = WorkflowExecution(
        id=execution_id,
        clinical_case_id=case_id,
        workflow_id="workflow-abc",
        trace_id="trace-xyz",
        external_case_id="case-1",
        external_patient_id="patient-1",
        context_id="ctx-1",
        status="completed",
        orchestration_status="completed",
        safety_status="requires_review",
        retrieval_mode="local_corpus",
        confidence_score=Decimal("0.8200"),
        evidence_metadata={},
        risk_metadata={},
        safety_metadata={},
        escalation_metadata={},
        started_at=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 6, 19, 8, 0, 2, tzinfo=UTC),
        latency_ms=Decimal("2000.000"),
    )

    case_repo = AsyncMock()
    case_repo.resolve_for_workflow.return_value = clinical_case

    execution_repo = AsyncMock()
    execution_repo.insert.return_value = workflow_execution

    audit_service = AsyncMock(spec=WorkflowAuditService)

    session = MagicMock()
    service = WorkflowPersistenceService(
        session=session,
        case_repo=case_repo,
        execution_repo=execution_repo,
        audit_service=audit_service,
    )

    request_payload = {
        "case_id": "case-1",
        "patient_context": {
            "patient_id": "patient-1",
            "vitals": [],
            "labs": [],
            "medications": [],
        },
        "metadata": {},
        "evidence_corpus": [],
    }
    response_payload = {
        "workflow_id": "workflow-abc",
        "status": "completed",
        "case_id": "case-1",
        "patient_id": "patient-1",
        "context_id": "ctx-1",
        "orchestration_status": "completed",
        "safety_status": "requires_review",
        "confidence_scores": {"workflow": 0.82},
        "retrieval_metadata": {"retrieval_mode": "local_corpus"},
        "evidence": [],
        "citations": [],
        "risk_analysis": {"risk_level": "moderate", "contributing_factors": []},
        "escalation_indicators": [{"code": "human_review", "level": "warning", "message": "x"}],
        "safety_metadata": {"escalation": {"recommended_action": "human_review"}},
        "safety_events": [],
        "approval_requirements": {"required": True},
        "workflow_trace_ids": {
            "output_id": "output-1",
            "approval_id": "approval-1",
        },
        "failure_recovery": {},
        "trace": {
            "trace_id": "trace-xyz",
            "started_at": datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
            "completed_at": datetime(2026, 6, 19, 8, 0, 2, tzinfo=UTC),
            "latency_ms": 2000.0,
        },
        "generated_at": datetime(2026, 6, 19, 8, 0, 2, tzinfo=UTC),
    }

    persisted_id = await service.persist_completed_run(
        request_payload=request_payload,
        response_payload=response_payload,
        retrieval_mode="local_corpus",
        request_id="req-1",
        correlation_id="corr-1",
    )

    assert persisted_id == execution_id
    audit_service.record_completed.assert_awaited_once()
    audit_service.record_outcome_events.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_workflow_started_persists_started_audit() -> None:
    case_id = uuid4()
    clinical_case = ClinicalCase(
        id=case_id,
        external_case_id="case-1",
        patient_id=uuid4(),
        title="Case case-1",
        status="open",
        safety_status="pending",
        evidence_snapshot={},
    )
    case_repo = AsyncMock()
    case_repo.resolve_for_workflow.return_value = clinical_case
    audit_service = AsyncMock(spec=WorkflowAuditService)

    service = WorkflowPersistenceService(
        session=MagicMock(),
        case_repo=case_repo,
        audit_service=audit_service,
    )

    result = await service.record_workflow_started(
        request_payload={
            "case_id": "case-1",
            "patient_context": {"patient_id": "patient-1"},
        },
        retrieval_mode="local_corpus",
        request_id="req-1",
    )

    assert result == case_id
    audit_service.record_started.assert_awaited_once()
