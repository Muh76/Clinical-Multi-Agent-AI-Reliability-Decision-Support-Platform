from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from clinical_ai_platform.audit.events import WorkflowAuditEventType


AUDIT_SCHEMA_VERSION = "workflow-audit/v1"


class WorkflowAuditLinkage(BaseModel):
    """Trace and workflow identifiers shared across immutable audit records."""

    model_config = ConfigDict(extra="forbid")

    external_case_id: str
    external_patient_id: str | None = None
    workflow_id: str | None = None
    trace_id: str | None = None
    output_id: str | None = None
    approval_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    clinical_case_id: str | None = None
    workflow_execution_id: str | None = None


class WorkflowAuditEvent(BaseModel):
    """Immutable workflow audit event envelope stored in audit_logs.payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = AUDIT_SCHEMA_VERSION
    event_type: WorkflowAuditEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    linkage: WorkflowAuditLinkage
    detail: dict[str, Any] = Field(default_factory=dict)


class WorkflowAuditEventRecord(BaseModel):
    """Input record for append-only persistence."""

    model_config = ConfigDict(extra="forbid")

    event_type: WorkflowAuditEventType
    linkage: WorkflowAuditLinkage
    detail: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    clinical_case_id: UUID | None = None
    workflow_execution_id: UUID | None = None
    actor_id: str | None = None
    actor_type: str = "system"
    event_source: str = "workflow_audit"
