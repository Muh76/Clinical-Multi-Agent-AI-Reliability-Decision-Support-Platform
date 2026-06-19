from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_api.services.workflows import EvidenceGroundingWorkflowService
from clinical_ai_platform.persistence.workflow_persistence import WorkflowPersistenceService


@pytest.mark.asyncio
async def test_workflow_service_records_started_before_run() -> None:
    session = MagicMock(spec=AsyncSession)
    begin_context = MagicMock()
    begin_context.__aenter__ = AsyncMock(return_value=None)
    begin_context.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_context

    persistence = AsyncMock(spec=WorkflowPersistenceService)
    runner = AsyncMock()
    runner.run.return_value = _agent_output()

    service = EvidenceGroundingWorkflowService(
        session=session,
        runner=runner,
        agents_enabled=True,
        retrieval_mode="local_corpus",
        persist_workflows=True,
        persistence=persistence,
    )

    from clinical_ai_api.schemas.workflows import GroundedEvidenceWorkflowRequest
    from clinical_ai_multimodal.patient_context.schemas import RawPatientContext

    payload = GroundedEvidenceWorkflowRequest(
        case_id="case-1",
        patient_context=RawPatientContext(patient_id="patient-1"),
        evidence_corpus=[],
    )

    await service.run(payload=payload, request_id="req-1", correlation_id="corr-1")

    persistence.record_workflow_started.assert_awaited_once()
    persistence.persist_completed_run.assert_awaited_once()
    assert session.begin.call_count == 2


@pytest.mark.asyncio
async def test_workflow_service_persists_failure_audit() -> None:
    session = MagicMock(spec=AsyncSession)
    begin_context = MagicMock()
    begin_context.__aenter__ = AsyncMock(return_value=None)
    begin_context.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_context

    persistence = AsyncMock(spec=WorkflowPersistenceService)
    runner = AsyncMock()
    runner.run.side_effect = RuntimeError("boom")

    service = EvidenceGroundingWorkflowService(
        session=session,
        runner=runner,
        agents_enabled=True,
        retrieval_mode="local_corpus",
        persist_workflows=True,
        persistence=persistence,
    )

    from clinical_ai_api.schemas.workflows import GroundedEvidenceWorkflowRequest
    from clinical_ai_multimodal.patient_context.schemas import RawPatientContext

    payload = GroundedEvidenceWorkflowRequest(
        case_id="case-1",
        patient_context=RawPatientContext(patient_id="patient-1"),
        evidence_corpus=[],
    )

    with pytest.raises(Exception):
        await service.run(payload=payload, request_id="req-1")

    persistence.record_workflow_started.assert_awaited_once()
    persistence.persist_failed_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_service_persists_after_successful_run() -> None:
    session = MagicMock(spec=AsyncSession)
    begin_context = MagicMock()
    begin_context.__aenter__ = AsyncMock(return_value=None)
    begin_context.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_context

    persistence = AsyncMock(spec=WorkflowPersistenceService)
    runner = AsyncMock()
    runner.run.return_value = _agent_output()

    service = EvidenceGroundingWorkflowService(
        session=session,
        runner=runner,
        agents_enabled=True,
        retrieval_mode="local_corpus",
        persist_workflows=True,
        persistence=persistence,
    )

    from clinical_ai_api.schemas.workflows import GroundedEvidenceWorkflowRequest
    from clinical_ai_multimodal.patient_context.schemas import RawPatientContext

    payload = GroundedEvidenceWorkflowRequest(
        case_id="case-1",
        patient_context=RawPatientContext(patient_id="patient-1"),
        evidence_corpus=[],
    )

    response = await service.run(payload=payload, request_id="req-1", correlation_id="corr-1")

    assert response.workflow_id
    assert session.begin.call_count == 2
    persistence.persist_completed_run.assert_awaited_once()
    persist_kwargs = persistence.persist_completed_run.await_args.kwargs
    assert persist_kwargs["request_id"] == "req-1"
    assert persist_kwargs["correlation_id"] == "corr-1"
    assert persist_kwargs["retrieval_mode"] == "local_corpus"


@pytest.mark.asyncio
async def test_workflow_service_skips_persistence_when_disabled() -> None:
    session = MagicMock(spec=AsyncSession)
    persistence = AsyncMock(spec=WorkflowPersistenceService)
    runner = AsyncMock()
    runner.run.return_value = _agent_output()

    service = EvidenceGroundingWorkflowService(
        session=session,
        runner=runner,
        agents_enabled=True,
        retrieval_mode="local_corpus",
        persist_workflows=False,
        persistence=persistence,
    )

    from clinical_ai_api.schemas.workflows import GroundedEvidenceWorkflowRequest
    from clinical_ai_multimodal.patient_context.schemas import RawPatientContext

    payload = GroundedEvidenceWorkflowRequest(
        case_id="case-1",
        patient_context=RawPatientContext(patient_id="patient-1"),
        evidence_corpus=[],
    )

    await service.run(payload=payload)

    session.begin.assert_not_called()
    persistence.persist_completed_run.assert_not_awaited()


def _agent_output():
    from clinical_ai_agents.end_to_end import EndToEndWorkflowOutput
    from clinical_ai_agents.safety_aware_workflow import SafetyAwareWorkflowOutput

    base = EndToEndWorkflowOutput(
        output_id="output-1",
        workflow_id="workflow-abc",
        trace_id="trace-xyz",
        case_id="case-1",
        status="completed",
        structured_patient_context={"patient_id": "patient-1", "context_id": "ctx-1"},
        retrieved_evidence=[
            {
                "rank": 1,
                "source_id": "src-1",
                "source_type": "local_policy",
                "text": "Evidence text",
                "score": 0.9,
                "confidence_score": 0.9,
                "retrieval_score": 0.9,
                "source_reliability_score": 0.8,
                "metadata": {},
            }
        ],
        citations=[
            {
                "citation_id": "cite-1",
                "source_id": "src-1",
                "source_type": "local_policy",
                "attribution_text": "cite-1",
            }
        ],
        confidence_scores={"workflow": 0.8, "agents": {}},
        risk_analysis={
            "risk_level": "low",
            "risk_score": 0.2,
            "contributing_factors": [],
        },
        workflow_trace={
            "duration_ms": 100.0,
            "nodes": [
                {
                    "node_id": "patient_context",
                    "status": "completed",
                    "latency_ms": 10.0,
                    "agent_role": "patient_context",
                    "agent_run_id": "run-1",
                },
                {
                    "node_id": "evidence_retrieval",
                    "status": "completed",
                    "latency_ms": 40.0,
                    "agent_role": "evidence_retrieval",
                    "agent_run_id": "run-2",
                },
                {
                    "node_id": "risk_analysis",
                    "status": "completed",
                    "latency_ms": 50.0,
                    "agent_role": "risk_analysis",
                    "agent_run_id": "run-3",
                },
            ],
        },
    )
    return SafetyAwareWorkflowOutput(
        output_id="safety-output-1",
        workflow_id="workflow-abc",
        trace_id="trace-xyz",
        case_id="case-1",
        status="completed",
        base_workflow=base,
        hallucination_risk={"recommended_action": "continue", "grounding_confidence": 0.9},
        evidence_verification={"verification_confidence": 0.85},
        uncertainty={"uncertainty_score": 0.2},
        escalation={"interruption": {"requires_human_review": False}},
        safety_critic={"status": "evaluated"},
        approval={"state": "not_required"},
        approval_requirements={"required": False, "blocking": False},
    )
