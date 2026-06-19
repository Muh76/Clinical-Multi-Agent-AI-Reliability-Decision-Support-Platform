from __future__ import annotations

import pytest
from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.observability import (
    InMemoryRetrievalMetricsSink,
    StructuredRetrievalObserver,
)
from clinical_ai_retrieval.schemas import RetrievalBackend
from clinical_ai_retrieval.retrieval_service import RetrievalService
from clinical_ai_retrieval.retrievers.types import RetrieverOutput
from clinical_ai_retrieval.schemas import (
    EvidenceMetadata,
    EvidenceSourceType,
    FusionStrategy,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
)


class StubRetriever:
    backend = RetrievalBackend.LOCAL_CORPUS

    async def retrieve_candidates(self, context: RetrievalContext) -> RetrieverOutput:
        result = RetrievalResult(
            chunk_id="local:doc:0",
            document_id="local:doc",
            score=0.8,
            text="Vancomycin dosing should consider renal function.",
            metadata=EvidenceMetadata(
                source_type=EvidenceSourceType.LOCAL_POLICY,
                source_id="renal-dosing",
                title="Renal dosing policy",
                citation_id="local_policy:renal-dosing",
            ),
            lexical_score=0.8,
        )
        return RetrieverOutput(
            candidates=[result],
            backend=self.backend,
            bm25_result_count=1,
            retrieval_latency_ms=4.2,
        )


@pytest.mark.asyncio
async def test_retrieval_service_emits_trace_and_metrics() -> None:
    metrics = InMemoryRetrievalMetricsSink()
    observer = StructuredRetrievalObserver(metrics_sink=metrics)
    service = RetrievalService(retriever=StubRetriever(), observer=observer)
    context = RetrievalContext(
        query=RetrievalQuery(
            query="creatinine vancomycin renal dosing",
            limit=1,
            mode=RetrievalMode.BM25,
            fusion_strategy=FusionStrategy.WEIGHTED_SUM,
            rerank=False,
        ),
        workflow_id="workflow-1",
        workflow_trace_id="trace-1",
        agent_run_id="agent-run-1",
        case_id="case-1",
    )

    package = await service.retrieve_evidence(context)

    assert package.retrieval_trace_id is not None
    assert service.last_trace is not None
    assert service.last_trace.query_text == "creatinine vancomycin renal dosing"
    assert service.last_trace.latency.retrieval_ms >= 0.0
    assert service.last_trace.retrieved_document_count == 1
    assert service.last_trace.retrieval_source == RetrievalBackend.LOCAL_CORPUS
    assert len(metrics.retrievals) == 1
    assert metrics.retrievals[0].trace.retrieval_run_id == package.retrieval_trace_id


class FailingRetriever:
    async def retrieve_candidates(self, context: RetrievalContext) -> RetrieverOutput:
        raise RuntimeError("qdrant unavailable")


@pytest.mark.asyncio
async def test_retrieval_service_emits_failure_event() -> None:
    metrics = InMemoryRetrievalMetricsSink()
    observer = StructuredRetrievalObserver(metrics_sink=metrics)
    service = RetrievalService(retriever=FailingRetriever(), observer=observer)
    context = RetrievalContext(
        query=RetrievalQuery(query="renal dosing"),
        workflow_trace_id="trace-fail",
    )

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        await service.retrieve_evidence(context)

    assert service.last_failure is not None
    assert service.last_failure.error_type == "RuntimeError"
    assert len(metrics.failures) == 1
