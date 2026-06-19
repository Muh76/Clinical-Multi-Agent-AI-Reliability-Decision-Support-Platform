from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_platform.audit.schemas import WorkflowAuditEvent, WorkflowAuditEventRecord
from clinical_ai_platform.db.models.audit_log import AuditLog
from clinical_ai_platform.db.models.clinical_case import ClinicalCase
from clinical_ai_platform.db.models.patient import Patient
from clinical_ai_platform.db.models.workflow_execution import WorkflowExecution
from clinical_ai_platform.persistence.dto import WorkflowExecutionRecord


class SqlAlchemyClinicalCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_case_id(self, external_case_id: str) -> ClinicalCase | None:
        statement = select(ClinicalCase).where(
            ClinicalCase.external_case_id == external_case_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def resolve_for_workflow(
        self,
        *,
        external_case_id: str,
        external_patient_id: str,
        patient_context_metadata: dict[str, object],
        safety_status: str,
        evidence_snapshot: dict[str, object],
    ) -> ClinicalCase:
        existing = await self.get_by_external_case_id(external_case_id)
        if existing is not None:
            existing.safety_status = safety_status
            existing.evidence_snapshot = evidence_snapshot
            existing.summary = _case_summary(patient_context_metadata)
            return existing

        patient = await self._get_or_create_patient(external_patient_id)
        clinical_case = ClinicalCase(
            external_case_id=external_case_id,
            patient_id=patient.id,
            title=f"Case {external_case_id}",
            summary=_case_summary(patient_context_metadata),
            status="open",
            safety_status=safety_status,
            evidence_snapshot=evidence_snapshot,
        )
        self._session.add(clinical_case)
        await self._session.flush()
        return clinical_case

    async def _get_or_create_patient(self, external_patient_id: str) -> Patient:
        statement = select(Patient).where(Patient.external_patient_id == external_patient_id)
        result = await self._session.execute(statement)
        patient = result.scalar_one_or_none()
        if patient is not None:
            return patient

        patient = Patient(
            external_patient_id=external_patient_id,
            display_label=f"Patient {external_patient_id}",
            is_active=True,
        )
        self._session.add(patient)
        await self._session.flush()
        return patient


class SqlAlchemyWorkflowExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_workflow_id(self, workflow_id: str) -> WorkflowExecution | None:
        statement = select(WorkflowExecution).where(WorkflowExecution.workflow_id == workflow_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def insert(self, record: WorkflowExecutionRecord) -> WorkflowExecution:
        execution = WorkflowExecution(
            clinical_case_id=record.clinical_case_id,
            workflow_id=record.workflow_id,
            trace_id=record.trace_id,
            output_id=record.output_id,
            approval_id=record.approval_id,
            request_id=record.request_id,
            correlation_id=record.correlation_id,
            external_case_id=record.external_case_id,
            external_patient_id=record.external_patient_id,
            context_id=record.context_id,
            status=record.status,
            orchestration_status=record.orchestration_status,
            safety_status=record.safety_status,
            retrieval_mode=record.retrieval_mode,
            confidence_score=record.confidence_score,
            evidence_metadata=record.evidence_metadata,
            risk_metadata=record.risk_metadata,
            safety_metadata=record.safety_metadata,
            escalation_metadata=record.escalation_metadata,
            started_at=record.started_at,
            completed_at=record.completed_at,
            latency_ms=record.latency_ms,
        )
        self._session.add(execution)
        await self._session.flush()
        return execution


class SqlAlchemyAuditLogRepository:
    """Append-only audit log repository. Records are never updated or deleted."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        clinical_case_id: UUID | None = None,
        workflow_execution_id: UUID | None = None,
        actor_id: str | None = None,
        actor_type: str = "system",
        event_source: str = "workflow_persistence",
    ) -> AuditLog:
        audit_log = AuditLog(
            clinical_case_id=clinical_case_id,
            workflow_execution_id=workflow_execution_id,
            actor_id=actor_id,
            actor_type=actor_type,
            event_type=event_type,
            event_source=event_source,
            payload=payload,
        )
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def append_many(self, records: list[WorkflowAuditEventRecord]) -> list[AuditLog]:
        audit_logs: list[AuditLog] = []
        for record in records:
            event = WorkflowAuditEvent(
                event_type=record.event_type,
                occurred_at=record.occurred_at,
                linkage=record.linkage,
                detail=record.detail,
            )
            audit_log = AuditLog(
                clinical_case_id=record.clinical_case_id,
                workflow_execution_id=record.workflow_execution_id,
                actor_id=record.actor_id,
                actor_type=record.actor_type,
                event_type=record.event_type.value,
                event_source=record.event_source,
                payload=event.model_dump(mode="json"),
            )
            self._session.add(audit_log)
            audit_logs.append(audit_log)
        await self._session.flush()
        return audit_logs

    async def list_for_workflow_execution(
        self,
        workflow_execution_id: UUID,
    ) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.workflow_execution_id == workflow_execution_id)
            .order_by(AuditLog.created_at.asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())


def _case_summary(patient_context_metadata: dict[str, object]) -> str:
    vitals = patient_context_metadata.get("vitals_count", 0)
    labs = patient_context_metadata.get("labs_count", 0)
    medications = patient_context_metadata.get("medications_count", 0)
    return (
        f"Reliability case with vitals={vitals}, labs={labs}, medications={medications}"
    )
