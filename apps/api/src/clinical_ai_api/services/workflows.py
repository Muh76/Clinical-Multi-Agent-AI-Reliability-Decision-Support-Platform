from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_agents import SafetyAwareClinicalWorkflowRunner
from clinical_ai_api.core.agent_container import SAFETY_AWARE_WORKFLOW_EXECUTION_ORDER
from clinical_ai_api.core.errors import AppError
from clinical_ai_api.schemas.workflows import (
    GroundedEvidenceWorkflowRequest,
    GroundedEvidenceWorkflowResponse,
    WorkflowStatus,
)
from clinical_ai_api.services.workflow_mapping import (
    from_safety_aware_output,
    to_safety_aware_request,
)
from clinical_ai_platform.observability import bind_execution_context, get_logger


logger = get_logger(__name__)


class AgentsDisabledError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="agents_disabled",
            message="Agent workflows are disabled by server configuration.",
            status_code=503,
        )


class EvidenceGroundingWorkflowService:
    """Runs the full clinical reliability pipeline via SafetyAwareClinicalWorkflowRunner."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        runner: SafetyAwareClinicalWorkflowRunner,
        agents_enabled: bool,
        retrieval_mode: str,
    ) -> None:
        self._session = session
        self._runner = runner
        self._agents_enabled = agents_enabled
        self._retrieval_mode = retrieval_mode

    async def run(
        self,
        *,
        payload: GroundedEvidenceWorkflowRequest,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GroundedEvidenceWorkflowResponse:
        _ = self._session
        if not self._agents_enabled:
            raise AgentsDisabledError()

        bind_execution_context(case_id=payload.case_id)
        logger.info(
            "clinical_reliability_workflow_started",
            case_id=payload.case_id,
            request_id=request_id,
            correlation_id=correlation_id,
            retrieval_mode=self._retrieval_mode,
            runner="SafetyAwareClinicalWorkflowRunner",
            workflow_execution_order=list(SAFETY_AWARE_WORKFLOW_EXECUTION_ORDER),
        )

        try:
            agent_request = to_safety_aware_request(payload)
            agent_output = await self._runner.run(
                agent_request,
                request_id=request_id,
                correlation_id=correlation_id,
            )
            response = from_safety_aware_output(
                payload=payload,
                output=agent_output,
                request_id=request_id,
                correlation_id=correlation_id,
                retrieval_mode=self._retrieval_mode,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.exception(
                "clinical_reliability_workflow_failed",
                case_id=payload.case_id,
                request_id=request_id,
                correlation_id=correlation_id,
                error_type=type(exc).__name__,
            )
            raise AppError(
                code="clinical_reliability_workflow_failed",
                message="Clinical reliability workflow failed before a response could be produced.",
                status_code=500,
            ) from exc

        if response.status == WorkflowStatus.FAILED:
            logger.error(
                "clinical_reliability_workflow_failed",
                workflow_id=response.workflow_id,
                trace_id=response.trace.trace_id,
                case_id=payload.case_id,
                orchestration_status=response.orchestration_status,
                safety_status=response.safety_status,
            )
            raise AppError(
                code="clinical_reliability_workflow_failed",
                message="Clinical reliability workflow completed with a failed agent execution.",
                status_code=500,
            )

        logger.info(
            "clinical_reliability_workflow_completed",
            workflow_id=response.workflow_id,
            trace_id=response.trace.trace_id,
            case_id=payload.case_id,
            request_id=request_id,
            correlation_id=correlation_id,
            orchestration_status=response.orchestration_status,
            safety_status=response.safety_status,
            evidence_count=len(response.evidence),
            citation_count=len(response.citations),
            confidence_score=response.confidence_score,
            risk_level=response.risk_analysis.get("risk_level"),
            escalation_indicator_count=len(response.escalation_indicators),
            approval_required=response.approval_requirements.required,
            safety_event_count=len(response.safety_events),
        )
        return response
