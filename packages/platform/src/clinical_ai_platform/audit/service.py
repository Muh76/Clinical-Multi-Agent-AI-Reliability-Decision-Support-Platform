from __future__ import annotations

from typing import Any
from uuid import UUID

from clinical_ai_platform.audit.events import WorkflowAuditEventType
from clinical_ai_platform.audit.extractors import (
    approval_audit_details,
    escalation_audit_details,
    linkage_from_request,
    linkage_from_response,
    retrieval_failed_audit_details,
    safety_blocked_audit_details,
)
from clinical_ai_platform.audit.schemas import (
    WorkflowAuditEventRecord,
    WorkflowAuditLinkage,
)
from clinical_ai_platform.db.models.audit_log import AuditLog
from clinical_ai_platform.db.repositories import SqlAlchemyAuditLogRepository


class WorkflowAuditService:
    """Append-only workflow audit recorder with trace and execution linkage."""

    def __init__(self, audit_repo: SqlAlchemyAuditLogRepository) -> None:
        self._audit_repo = audit_repo

    async def record_started(
        self,
        *,
        request_payload: dict[str, Any],
        retrieval_mode: str,
        request_id: str | None,
        correlation_id: str | None,
        clinical_case_id: UUID | None = None,
    ) -> AuditLog:
        linkage = WorkflowAuditLinkage.model_validate(
            linkage_from_request(
                request_payload,
                request_id=request_id,
                correlation_id=correlation_id,
                clinical_case_id=str(clinical_case_id) if clinical_case_id else None,
            ),
        )
        return await self._append(
            WorkflowAuditEventRecord(
                event_type=WorkflowAuditEventType.WORKFLOW_STARTED,
                linkage=linkage,
                detail={
                    "retrieval_mode": retrieval_mode,
                    "require_human_approval_checkpoint": request_payload.get(
                        "require_human_approval_checkpoint",
                    ),
                    "top_k": request_payload.get("top_k"),
                },
                clinical_case_id=clinical_case_id,
            ),
        )

    async def record_completed(
        self,
        *,
        response_payload: dict[str, Any],
        request_id: str | None,
        correlation_id: str | None,
        clinical_case_id: UUID,
        workflow_execution_id: UUID,
    ) -> AuditLog:
        linkage = WorkflowAuditLinkage.model_validate(
            linkage_from_response(
                response_payload,
                request_id=request_id,
                correlation_id=correlation_id,
                clinical_case_id=str(clinical_case_id),
                workflow_execution_id=str(workflow_execution_id),
            ),
        )
        trace = response_payload.get("trace", {})
        latency_ms = trace.get("latency_ms", 0.0) if isinstance(trace, dict) else 0.0
        return await self._append(
            WorkflowAuditEventRecord(
                event_type=WorkflowAuditEventType.WORKFLOW_COMPLETED,
                linkage=linkage,
                detail={
                    "status": response_payload.get("status"),
                    "safety_status": response_payload.get("safety_status"),
                    "orchestration_status": response_payload.get("orchestration_status"),
                    "confidence_score": (
                        response_payload.get("confidence_scores", {}).get("workflow")
                        if isinstance(response_payload.get("confidence_scores"), dict)
                        else None
                    ),
                    "latency_ms": latency_ms,
                },
                clinical_case_id=clinical_case_id,
                workflow_execution_id=workflow_execution_id,
            ),
        )

    async def record_failed(
        self,
        *,
        request_payload: dict[str, Any],
        request_id: str | None,
        correlation_id: str | None,
        error_code: str,
        error_message: str,
        clinical_case_id: UUID | None = None,
        workflow_execution_id: UUID | None = None,
        response_payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        if response_payload is not None:
            linkage_data = linkage_from_response(
                response_payload,
                request_id=request_id,
                correlation_id=correlation_id,
                clinical_case_id=str(clinical_case_id) if clinical_case_id else None,
                workflow_execution_id=(
                    str(workflow_execution_id) if workflow_execution_id else None
                ),
            )
        else:
            linkage_data = linkage_from_request(
                request_payload,
                request_id=request_id,
                correlation_id=correlation_id,
                clinical_case_id=str(clinical_case_id) if clinical_case_id else None,
            )
        linkage = WorkflowAuditLinkage.model_validate(linkage_data)
        return await self._append(
            WorkflowAuditEventRecord(
                event_type=WorkflowAuditEventType.WORKFLOW_FAILED,
                linkage=linkage,
                detail={
                    "error_code": error_code,
                    "error_message": error_message,
                    "status": (
                        response_payload.get("status") if response_payload is not None else None
                    ),
                    "safety_status": (
                        response_payload.get("safety_status")
                        if response_payload is not None
                        else None
                    ),
                    "orchestration_status": (
                        response_payload.get("orchestration_status")
                        if response_payload is not None
                        else None
                    ),
                },
                clinical_case_id=clinical_case_id,
                workflow_execution_id=workflow_execution_id,
            ),
        )

    async def record_outcome_events(
        self,
        *,
        response_payload: dict[str, Any],
        request_id: str | None,
        correlation_id: str | None,
        clinical_case_id: UUID,
        workflow_execution_id: UUID,
    ) -> list[AuditLog]:
        linkage = WorkflowAuditLinkage.model_validate(
            linkage_from_response(
                response_payload,
                request_id=request_id,
                correlation_id=correlation_id,
                clinical_case_id=str(clinical_case_id),
                workflow_execution_id=str(workflow_execution_id),
            ),
        )
        records: list[WorkflowAuditEventRecord] = []

        escalation_detail = escalation_audit_details(response_payload)
        if escalation_detail is not None:
            records.append(
                WorkflowAuditEventRecord(
                    event_type=WorkflowAuditEventType.ESCALATION_TRIGGERED,
                    linkage=linkage,
                    detail=escalation_detail,
                    clinical_case_id=clinical_case_id,
                    workflow_execution_id=workflow_execution_id,
                ),
            )

        approval_detail = approval_audit_details(response_payload)
        if approval_detail is not None:
            records.append(
                WorkflowAuditEventRecord(
                    event_type=WorkflowAuditEventType.APPROVAL_REQUIRED,
                    linkage=linkage,
                    detail=approval_detail,
                    clinical_case_id=clinical_case_id,
                    workflow_execution_id=workflow_execution_id,
                ),
            )

        blocked_detail = safety_blocked_audit_details(response_payload)
        if blocked_detail is not None:
            records.append(
                WorkflowAuditEventRecord(
                    event_type=WorkflowAuditEventType.SAFETY_BLOCKED,
                    linkage=linkage,
                    detail=blocked_detail,
                    clinical_case_id=clinical_case_id,
                    workflow_execution_id=workflow_execution_id,
                ),
            )

        retrieval_detail = retrieval_failed_audit_details(response_payload)
        if retrieval_detail is not None:
            records.append(
                WorkflowAuditEventRecord(
                    event_type=WorkflowAuditEventType.RETRIEVAL_FAILED,
                    linkage=linkage,
                    detail=retrieval_detail,
                    clinical_case_id=clinical_case_id,
                    workflow_execution_id=workflow_execution_id,
                ),
            )

        return await self._audit_repo.append_many(records)

    async def _append(self, record: WorkflowAuditEventRecord) -> AuditLog:
        results = await self._audit_repo.append_many([record])
        return results[0]
