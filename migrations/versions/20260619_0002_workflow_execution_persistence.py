"""add workflow execution persistence tables

Revision ID: 20260619_0002
Revises: 20260518_0001
Create Date: 2026-06-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260619_0002"
down_revision: str | None = "20260518_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinical_cases",
        sa.Column("external_case_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_clinical_cases_external_case_id"),
        "clinical_cases",
        ["external_case_id"],
    )

    op.create_table(
        "workflow_executions",
        sa.Column("clinical_case_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("output_id", sa.String(length=128), nullable=True),
        sa.Column("approval_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("external_case_id", sa.String(length=128), nullable=False),
        sa.Column("external_patient_id", sa.String(length=128), nullable=False),
        sa.Column("context_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("orchestration_status", sa.String(length=64), nullable=False),
        sa.Column("safety_status", sa.String(length=64), nullable=False),
        sa.Column("retrieval_mode", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column(
            "evidence_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "risk_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "safety_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "escalation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["clinical_case_id"],
            ["clinical_cases.id"],
            name=op.f("fk_workflow_executions_clinical_case_id_clinical_cases"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_executions")),
        sa.UniqueConstraint("workflow_id", name=op.f("uq_workflow_executions_workflow_id")),
    )
    op.create_index(
        "ix_workflow_executions_trace_id",
        "workflow_executions",
        ["trace_id"],
    )
    op.create_index(
        "ix_workflow_executions_clinical_case_id",
        "workflow_executions",
        ["clinical_case_id"],
    )
    op.create_index(
        "ix_workflow_executions_external_case_id",
        "workflow_executions",
        ["external_case_id"],
    )
    op.create_index(
        "ix_workflow_executions_completed_at",
        "workflow_executions",
        ["completed_at"],
    )

    op.add_column(
        "audit_logs",
        sa.Column("workflow_execution_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_audit_logs_workflow_execution_id_workflow_executions"),
        "audit_logs",
        "workflow_executions",
        ["workflow_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_audit_logs_workflow_execution_id",
        "audit_logs",
        ["workflow_execution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_workflow_execution_id", table_name="audit_logs")
    op.drop_constraint(
        op.f("fk_audit_logs_workflow_execution_id_workflow_executions"),
        "audit_logs",
        type_="foreignkey",
    )
    op.drop_column("audit_logs", "workflow_execution_id")

    op.drop_index("ix_workflow_executions_completed_at", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_external_case_id", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_clinical_case_id", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_trace_id", table_name="workflow_executions")
    op.drop_table("workflow_executions")

    op.drop_constraint(
        op.f("uq_clinical_cases_external_case_id"),
        "clinical_cases",
        type_="unique",
    )
    op.drop_column("clinical_cases", "external_case_id")
