from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_platform.audit.service import WorkflowAuditService
from clinical_ai_platform.db.repositories import (
    SqlAlchemyAuditLogRepository,
    SqlAlchemyClinicalCaseRepository,
    SqlAlchemyWorkflowExecutionRepository,
)
from clinical_ai_platform.persistence.dto import WorkflowExecutionRecord
from clinical_ai_platform.persistence.mappers import (
    evidence_snapshot_from_response,
    patient_context_metadata_from_request,
    workflow_execution_record_from_response,
)


class WorkflowPersistenceService:
    """Persists workflow runs with immutable audit trail linkage."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        case_repo: SqlAlchemyClinicalCaseRepository | None = None,
        execution_repo: SqlAlchemyWorkflowExecutionRepository | None = None,
        audit_repo: SqlAlchemyAuditLogRepository | None = None,
        audit_service: WorkflowAuditService | None = None,
    ) -> None:
        self._session = session
        self._case_repo = case_repo or SqlAlchemyClinicalCaseRepository(session)
        self._execution_repo = execution_repo or SqlAlchemyWorkflowExecutionRepository(session)
        audit_repository = audit_repo or SqlAlchemyAuditLogRepository(session)
        self._audit_repo = audit_repository
        self._audit_service = audit_service or WorkflowAuditService(audit_repository)

    async def record_workflow_started(
        self,
        *,
        request_payload: dict[str, Any],
        retrieval_mode: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID | None:
        patient_context = request_payload.get("patient_context", {})
        if not isinstance(patient_context, dict):
            patient_context = {}
        external_patient_id = str(patient_context.get("patient_id", "unknown"))
        patient_context_metadata = patient_context_metadata_from_request(request_payload)

        clinical_case = await self._case_repo.resolve_for_workflow(
            external_case_id=str(request_payload["case_id"]),
            external_patient_id=external_patient_id,
            patient_context_metadata=patient_context_metadata,
            safety_status="pending",
            evidence_snapshot={},
        )
        await self._audit_service.record_started(
            request_payload=request_payload,
            retrieval_mode=retrieval_mode,
            request_id=request_id,
            correlation_id=correlation_id,
            clinical_case_id=clinical_case.id,
        )
        return clinical_case.id

    async def persist_completed_run(
        self,
        *,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        retrieval_mode: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        patient_context_metadata = patient_context_metadata_from_request(request_payload)
        evidence_snapshot = evidence_snapshot_from_response(response_payload)
        safety_status = str(response_payload.get("safety_status", "completed"))

        clinical_case = await self._case_repo.resolve_for_workflow(
            external_case_id=str(request_payload["case_id"]),
            external_patient_id=str(response_payload["patient_id"]),
            patient_context_metadata=patient_context_metadata,
            safety_status=safety_status,
            evidence_snapshot=evidence_snapshot,
        )

        record_data = workflow_execution_record_from_response(
            response=response_payload,
            retrieval_mode=retrieval_mode,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        record = _to_execution_record(record_data, clinical_case_id=clinical_case.id)
        execution = await self._execution_repo.insert(record)

        await self._audit_service.record_completed(
            response_payload=response_payload,
            request_id=request_id,
            correlation_id=correlation_id,
            clinical_case_id=clinical_case.id,
            workflow_execution_id=execution.id,
        )
        await self._audit_service.record_outcome_events(
            response_payload=response_payload,
            request_id=request_id,
            correlation_id=correlation_id,
            clinical_case_id=clinical_case.id,
            workflow_execution_id=execution.id,
        )
        return execution.id

    async def persist_failed_run(
        self,
        *,
        request_payload: dict[str, Any],
        error_code: str,
        error_message: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
        response_payload: dict[str, Any] | None = None,
        retrieval_mode: str = "unknown",
    ) -> UUID | None:
        patient_context = request_payload.get("patient_context", {})
        if not isinstance(patient_context, dict):
            patient_context = {}
        external_patient_id = str(
            response_payload.get("patient_id")
            if response_payload is not None
            else patient_context.get("patient_id", "unknown"),
        )
        patient_context_metadata = patient_context_metadata_from_request(request_payload)
        safety_status = (
            str(response_payload.get("safety_status", "failed"))
            if response_payload is not None
            else "failed"
        )
        evidence_snapshot = (
            evidence_snapshot_from_response(response_payload)
            if response_payload is not None
            else {}
        )

        clinical_case = await self._case_repo.resolve_for_workflow(
            external_case_id=str(request_payload["case_id"]),
            external_patient_id=external_patient_id,
            patient_context_metadata=patient_context_metadata,
            safety_status=safety_status,
            evidence_snapshot=evidence_snapshot,
        )

        workflow_execution_id: UUID | None = None
        if response_payload is not None:
            record_data = workflow_execution_record_from_response(
                response=response_payload,
                retrieval_mode=retrieval_mode,
                request_id=request_id,
                correlation_id=correlation_id,
            )
            record_data["status"] = "failed"
            record = _to_execution_record(record_data, clinical_case_id=clinical_case.id)
            execution = await self._execution_repo.insert(record)
            workflow_execution_id = execution.id

        await self._audit_service.record_failed(
            request_payload=request_payload,
            request_id=request_id,
            correlation_id=correlation_id,
            error_code=error_code,
            error_message=error_message,
            clinical_case_id=clinical_case.id,
            workflow_execution_id=workflow_execution_id,
            response_payload=response_payload,
        )

        if response_payload is not None and workflow_execution_id is not None:
            await self._audit_service.record_outcome_events(
                response_payload=response_payload,
                request_id=request_id,
                correlation_id=correlation_id,
                clinical_case_id=clinical_case.id,
                workflow_execution_id=workflow_execution_id,
            )

        return workflow_execution_id


def _to_execution_record(
    data: dict[str, Any],
    *,
    clinical_case_id: UUID,
) -> WorkflowExecutionRecord:
    started_at = data["started_at"]
    completed_at = data["completed_at"]
    if not isinstance(started_at, datetime):
        raise TypeError("workflow trace started_at must be a datetime")
    if not isinstance(completed_at, datetime):
        raise TypeError("workflow trace completed_at must be a datetime")

    return WorkflowExecutionRecord(
        clinical_case_id=clinical_case_id,
        workflow_id=str(data["workflow_id"]),
        trace_id=str(data["trace_id"]),
        output_id=_optional_str(data.get("output_id")),
        approval_id=_optional_str(data.get("approval_id")),
        request_id=_optional_str(data.get("request_id")),
        correlation_id=_optional_str(data.get("correlation_id")),
        external_case_id=str(data["external_case_id"]),
        external_patient_id=str(data["external_patient_id"]),
        context_id=str(data["context_id"]),
        status=str(data["status"]),
        orchestration_status=str(data["orchestration_status"]),
        safety_status=str(data["safety_status"]),
        retrieval_mode=str(data["retrieval_mode"]),
        confidence_score=data["confidence_score"]
        if isinstance(data["confidence_score"], Decimal)
        else Decimal(str(data["confidence_score"])),
        evidence_metadata=_as_metadata_dict(data["evidence_metadata"]),
        risk_metadata=_as_metadata_dict(data["risk_metadata"]),
        safety_metadata=_as_metadata_dict(data["safety_metadata"]),
        escalation_metadata=_as_metadata_dict(data["escalation_metadata"]),
        started_at=started_at,
        completed_at=completed_at,
        latency_ms=data["latency_ms"]
        if isinstance(data["latency_ms"], Decimal)
        else Decimal(str(data["latency_ms"])),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_metadata_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}
