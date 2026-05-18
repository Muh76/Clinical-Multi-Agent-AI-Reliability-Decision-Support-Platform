from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from clinical_ai_platform.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from clinical_ai_platform.db.models.audit_log import AuditLog
    from clinical_ai_platform.db.models.patient import Patient


class ClinicalCase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clinical_cases"
    __table_args__ = (
        Index("ix_clinical_cases_patient_id", "patient_id"),
        Index("ix_clinical_cases_status", "status"),
        Index("ix_clinical_cases_safety_status", "safety_status"),
    )

    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="open")
    safety_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    evidence_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    patient: Mapped["Patient"] = relationship(back_populates="clinical_cases")
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="clinical_case",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

