from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WorkflowExecutionRecord:
    clinical_case_id: UUID | None
    workflow_id: str
    trace_id: str
    output_id: str | None
    approval_id: str | None
    request_id: str | None
    correlation_id: str | None
    external_case_id: str
    external_patient_id: str
    context_id: str
    status: str
    orchestration_status: str
    safety_status: str
    retrieval_mode: str
    confidence_score: Decimal
    evidence_metadata: dict[str, object]
    risk_metadata: dict[str, object]
    safety_metadata: dict[str, object]
    escalation_metadata: dict[str, object]
    started_at: datetime
    completed_at: datetime
    latency_ms: Decimal
