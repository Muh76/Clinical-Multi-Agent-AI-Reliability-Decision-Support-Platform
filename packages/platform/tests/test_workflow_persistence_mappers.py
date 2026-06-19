from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _sample_response() -> dict[str, Any]:
    return {
        "workflow_id": "workflow-abc",
        "status": "completed",
        "case_id": "case-1",
        "patient_id": "patient-1",
        "context_id": "ctx-1",
        "orchestration_status": "completed",
        "safety_status": "requires_review",
        "confidence_scores": {"workflow": 0.82, "agents": {}},
        "retrieval_metadata": {
            "query": "renal dosing",
            "retrieval_mode": "local_corpus",
            "candidate_count": 2,
            "retrieved_count": 1,
            "reranked": True,
            "top_k": 1,
            "context_id": "ctx-1",
            "patient_id": "patient-1",
            "validation_finding_count": 0,
            "safety_review_recommended": True,
        },
        "evidence": [
            {
                "rank": 1,
                "source_id": "local-renal-dosing",
                "source_type": "local_policy",
                "text": "Vancomycin dosing guidance.",
                "citation": {
                    "citation_id": "local_policy:local-renal-dosing",
                    "source_id": "local-renal-dosing",
                    "source_type": "local_policy",
                    "attribution_text": "local_policy:local-renal-dosing",
                },
                "score": 0.9,
                "confidence_score": 0.88,
                "retrieval_score": 0.91,
                "rerank_score": 0.9,
                "source_reliability_score": 0.85,
                "metadata": {"backend": "local"},
            }
        ],
        "citations": [
            {
                "citation_id": "local_policy:local-renal-dosing",
                "source_id": "local-renal-dosing",
                "source_type": "local_policy",
                "title": "Renal dosing policy",
                "attribution_text": "local_policy:local-renal-dosing",
            }
        ],
        "risk_analysis": {
            "risk_level": "moderate",
            "risk_score": 0.55,
            "contributing_factors": [{"code": "renal_impairment"}],
            "summary": "Moderate renal risk.",
        },
        "escalation_indicators": [
            {
                "code": "human_review",
                "level": "warning",
                "message": "Review recommended",
                "source": "escalation_logic",
            }
        ],
        "safety_metadata": {
            "hallucination_detection": {"recommended_action": "continue"},
            "evidence_verification": {"verification_confidence": 0.8},
            "uncertainty_scoring": {"uncertainty_score": 0.3},
            "escalation": {"interruption": {"requires_human_review": True}},
            "human_approval": {"state": "pending_review"},
            "safety_critic": {"status": "evaluated"},
        },
        "safety_events": [{"event_type": "safety_check", "status": "completed"}],
        "approval_requirements": {
            "required": True,
            "blocking": False,
            "state": "pending_review",
            "allow_workflow_resume": True,
            "allow_output_release": False,
        },
        "workflow_trace_ids": {
            "workflow_id": "workflow-abc",
            "trace_id": "trace-xyz",
            "output_id": "output-1",
            "approval_id": "approval-1",
        },
        "failure_recovery": {},
        "trace": {
            "workflow_id": "workflow-abc",
            "trace_id": "trace-xyz",
            "started_at": datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
            "completed_at": datetime(2026, 6, 19, 8, 0, 2, tzinfo=UTC),
            "latency_ms": 2000.0,
            "steps": [],
        },
        "generated_at": datetime(2026, 6, 19, 8, 0, 2, tzinfo=UTC),
    }


def test_evidence_metadata_from_response_extracts_scores() -> None:
    from clinical_ai_platform.persistence.mappers import evidence_metadata_from_response

    metadata = evidence_metadata_from_response(_sample_response())
    assert metadata["evidence_count"] == 1
    assert metadata["citation_count"] == 1
    assert metadata["evidence_items"][0]["source_id"] == "local-renal-dosing"
    assert metadata["retrieval_metadata"]["retrieval_mode"] == "local_corpus"


def test_risk_metadata_from_response_summarizes_risk() -> None:
    from clinical_ai_platform.persistence.mappers import risk_metadata_from_response

    metadata = risk_metadata_from_response(_sample_response())
    assert metadata["risk_level"] == "moderate"
    assert metadata["risk_score"] == 0.55
    assert metadata["contributing_factor_count"] == 1
    assert metadata["escalation_indicator_count"] == 1


def test_safety_metadata_from_response_includes_approval() -> None:
    from clinical_ai_platform.persistence.mappers import safety_metadata_from_response

    metadata = safety_metadata_from_response(_sample_response())
    assert metadata["safety_status"] == "requires_review"
    assert metadata["safety_event_count"] == 1
    assert metadata["approval_requirements"]["required"] is True


def test_escalation_metadata_from_response_includes_indicators() -> None:
    from clinical_ai_platform.persistence.mappers import escalation_metadata_from_response

    metadata = escalation_metadata_from_response(_sample_response())
    assert len(metadata["escalation_indicators"]) == 1
    assert metadata["escalation_decision"]["interruption"]["requires_human_review"] is True


def test_workflow_execution_record_from_response_maps_trace_ids() -> None:
    from clinical_ai_platform.persistence.mappers import workflow_execution_record_from_response

    record = workflow_execution_record_from_response(
        response=_sample_response(),
        retrieval_mode="local_corpus",
        request_id="req-1",
        correlation_id="corr-1",
    )
    assert record["workflow_id"] == "workflow-abc"
    assert record["trace_id"] == "trace-xyz"
    assert record["output_id"] == "output-1"
    assert record["approval_id"] == "approval-1"
    assert record["request_id"] == "req-1"
    assert record["status"] == "completed"
