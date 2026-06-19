from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from clinical_ai_platform.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from clinical_ai_platform.db.models.audit_log import AuditLog
    from clinical_ai_platform.db.models.clinical_case import ClinicalCase


class WorkflowExecution(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_executions"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_workflow_executions_workflow_id"),
        Index("ix_workflow_executions_trace_id", "trace_id"),
        Index("ix_workflow_executions_clinical_case_id", "clinical_case_id"),
        Index("ix_workflow_executions_external_case_id", "external_case_id"),
        Index("ix_workflow_executions_completed_at", "completed_at"),
    )

    clinical_case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    output_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_patient_id: Mapped[str] = mapped_column(String(128), nullable=False)
    context_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    orchestration_status: Mapped[str] = mapped_column(String(64), nullable=False)
    safety_status: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    risk_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    safety_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    escalation_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime] = mapped_column(nullable=False)
    latency_ms: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    clinical_case: Mapped["ClinicalCase | None"] = relationship(back_populates="workflow_executions")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="workflow_execution")
