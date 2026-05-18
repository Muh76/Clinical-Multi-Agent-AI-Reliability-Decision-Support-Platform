"""initial clinical tables

Revision ID: 20260518_0001
Revises:
Create Date: 2026-05-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260518_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("external_patient_id", sa.String(length=128), nullable=True),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column("risk_tier", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patients")),
    )
    op.create_index("ix_patients_external_patient_id", "patients", ["external_patient_id"])
    op.create_index("ix_patients_risk_tier", "patients", ["risk_tier"])

    op.create_table(
        "clinical_cases",
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("safety_status", sa.String(length=64), nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_clinical_cases_patient_id_patients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinical_cases")),
    )
    op.create_index("ix_clinical_cases_patient_id", "clinical_cases", ["patient_id"])
    op.create_index("ix_clinical_cases_safety_status", "clinical_cases", ["safety_status"])
    op.create_index("ix_clinical_cases_status", "clinical_cases", ["status"])

    op.create_table(
        "audit_logs",
        sa.Column("clinical_case_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_source", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_audit_logs_clinical_case_id_clinical_cases"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_clinical_case_id", "audit_logs", ["clinical_case_id"])
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_clinical_case_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_clinical_cases_status", table_name="clinical_cases")
    op.drop_index("ix_clinical_cases_safety_status", table_name="clinical_cases")
    op.drop_index("ix_clinical_cases_patient_id", table_name="clinical_cases")
    op.drop_table("clinical_cases")

    op.drop_index("ix_patients_risk_tier", table_name="patients")
    op.drop_index("ix_patients_external_patient_id", table_name="patients")
    op.drop_table("patients")
