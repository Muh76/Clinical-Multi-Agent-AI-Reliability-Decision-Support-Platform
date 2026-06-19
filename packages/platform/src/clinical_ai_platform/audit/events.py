from enum import StrEnum


class WorkflowAuditEventType(StrEnum):
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    ESCALATION_TRIGGERED = "workflow.escalation_triggered"
    APPROVAL_REQUIRED = "workflow.approval_required"
    SAFETY_BLOCKED = "workflow.safety_blocked"
    RETRIEVAL_FAILED = "workflow.retrieval_failed"


IMMUTABLE_WORKFLOW_AUDIT_EVENTS: frozenset[WorkflowAuditEventType] = frozenset(
    WorkflowAuditEventType
)
