from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from clinical_ai_agents.contracts import AgentInput, AgentRole, AgentRunStatus, AgentTraceContext
from clinical_ai_agents.evidence_retrieval import EvidenceRetrievalAgent
from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.retrieval_service import RetrievalService
from clinical_ai_retrieval.schemas import (
    Citation,
    EvidenceMetadata,
    EvidencePackage,
    EvidenceSourceType,
    FusionStrategy,
    RetrievalBackend,
    RetrievalDiagnostics,
    RetrievalEvidenceItem,
    RetrievalMode,
)


def _trace() -> AgentTraceContext:
    return AgentTraceContext(
        workflow_id="workflow-test",
        trace_id="trace-test",
        agent_run_id="agent-run-test",
    )


def _stub_evidence_package() -> EvidencePackage:
    metadata = EvidenceMetadata(
        source_type=EvidenceSourceType.LOCAL_POLICY,
        source_id="renal-dosing",
        title="Renal dosing policy",
        citation_id="local_policy:renal-dosing",
        evidence_level="guideline",
    )
    citation = Citation(
        citation_id="local_policy:renal-dosing",
        source_type=EvidenceSourceType.LOCAL_POLICY,
        source_id="renal-dosing",
        title="Renal dosing policy",
        attribution_text="Renal dosing policy. local policy: renal-dosing.",
    )
    evidence_item = RetrievalEvidenceItem(
        chunk_id="local_policy:renal-dosing:0",
        document_id="local_policy:renal-dosing",
        text="Vancomycin dosing should consider renal function and creatinine trends.",
        citation=citation,
        metadata=metadata,
        score=0.88,
        confidence_score=0.82,
        source_reliability_score=0.9,
        rank=1,
        scoring_components={"final": 0.88, "confidence": 0.82, "source_reliability": 0.9},
    )
    return EvidencePackage(
        query="creatinine vancomycin renal dosing",
        evidence=[evidence_item],
        citations=[citation],
        diagnostics=RetrievalDiagnostics(
            mode=RetrievalMode.HYBRID,
            fusion_strategy=FusionStrategy.WEIGHTED_SUM,
            backend=RetrievalBackend.QDRANT,
            dense_result_count=1,
            bm25_result_count=0,
            reranked=True,
        ),
        confidence_score=0.82,
    )


@pytest.mark.asyncio
async def test_evidence_retrieval_agent_delegates_to_retrieval_service() -> None:
    retrieval_service = AsyncMock(spec=RetrievalService)
    retrieval_service.retrieve_evidence = AsyncMock(return_value=_stub_evidence_package())

    agent = EvidenceRetrievalAgent(retrieval_service=retrieval_service)
    output = await agent.run(
        AgentInput(
            case_id="case-1",
            role=AgentRole.EVIDENCE_RETRIEVAL,
            trace=_trace(),
            payload={
                "evidence_query": "creatinine vancomycin renal dosing",
                "top_k": 1,
            },
        )
    )

    retrieval_service.retrieve_evidence.assert_awaited_once()
    context = retrieval_service.retrieve_evidence.await_args.args[0]
    assert isinstance(context, RetrievalContext)
    assert context.query.query == "creatinine vancomycin renal dosing"
    assert output.status == AgentRunStatus.COMPLETED
    assert output.explainability["retrieval_backend"] == "qdrant"
    assert output.structured_payload["evidence_package"]["evidence"][0]["source_id"] == "renal-dosing"


@pytest.mark.asyncio
async def test_evidence_retrieval_agent_has_no_internal_retrieval_methods() -> None:
    public_retrieval_methods = {
        name
        for name in dir(EvidenceRetrievalAgent)
        if "retrieve" in name.lower() and not name.startswith("_")
    }
    assert public_retrieval_methods == set()
