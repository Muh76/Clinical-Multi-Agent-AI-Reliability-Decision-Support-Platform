from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clinical_ai_platform.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from clinical_ai_platform.db.models.clinical_case import ClinicalCase


class Patient(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patients_external_patient_id", "external_patient_id"),
        Index("ix_patients_risk_tier", "risk_tier"),
    )

    external_patient_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_label: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    clinical_cases: Mapped[list["ClinicalCase"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

