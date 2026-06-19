from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from clinical_ai_platform.audit.events import WorkflowAuditEventType
from clinical_ai_platform.audit.schemas import WorkflowAuditEventRecord, WorkflowAuditLinkage
from clinical_ai_platform.db.repositories import SqlAlchemyAuditLogRepository


@pytest.mark.asyncio
async def test_append_many_writes_immutable_envelope_to_payload() -> None:
    session = AsyncMock()
    session.add = lambda obj: None
    session.flush = AsyncMock()

    repo = SqlAlchemyAuditLogRepository(session)
    case_id = uuid4()
    execution_id = uuid4()
    occurred_at = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)

    records = [
        WorkflowAuditEventRecord(
            event_type=WorkflowAuditEventType.WORKFLOW_COMPLETED,
            occurred_at=occurred_at,
            linkage=WorkflowAuditLinkage(
                external_case_id="case-1",
                workflow_id="workflow-abc",
                trace_id="trace-xyz",
                clinical_case_id=str(case_id),
                workflow_execution_id=str(execution_id),
            ),
            detail={"status": "completed"},
            clinical_case_id=case_id,
            workflow_execution_id=execution_id,
        ),
    ]

    audit_logs = await repo.append_many(records)

    assert len(audit_logs) == 1
    audit_log = audit_logs[0]
    assert audit_log.event_type == "workflow.completed"
    assert audit_log.clinical_case_id == case_id
    assert audit_log.workflow_execution_id == execution_id
    assert audit_log.payload["schema_version"] == "workflow-audit/v1"
    assert "occurred_at" in audit_log.payload
    assert audit_log.payload["linkage"]["trace_id"] == "trace-xyz"
    session.flush.assert_awaited_once()
