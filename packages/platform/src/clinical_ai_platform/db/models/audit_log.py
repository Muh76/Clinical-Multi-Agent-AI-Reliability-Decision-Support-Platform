from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from clinical_ai_platform.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from clinical_ai_platform.db.models.clinical_case import ClinicalCase


class AuditLog(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_clinical_case_id", "clinical_case_id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_event_type", "event_type"),
    )

    clinical_case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinical_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_source: Mapped[str] = mapped_column(String(128), nullable=False, default="api")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    clinical_case: Mapped[ClinicalCase | None] = relationship(back_populates="audit_logs")
