from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from clinical_ai_platform.observability import get_logger
from pydantic import Field

from clinical_ai_retrieval.schemas import RetrievalBackend, RetrievalModel


logger = get_logger(__name__)


class RetrievalEventType(StrEnum):
    RETRIEVAL_COMPLETED = "retrieval.completed"
    RETRIEVAL_FAILED = "retrieval.failed"


class QdrantSearchMetadata(RetrievalModel):
    collection_name: str
    vector_size: int | None = None
    search_limit: int = Field(ge=1)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    filters_applied: bool = False
    with_payload: bool = True
    with_vectors: bool = False
    embedding_model: str | None = None
    embedding_latency_ms: float | None = Field(default=None, ge=0.0)
    search_latency_ms: float | None = Field(default=None, ge=0.0)
    points_returned: int = Field(default=0, ge=0)


class RetrievalLatencyBreakdown(RetrievalModel):
    total_ms: float = Field(ge=0.0)
    retrieval_ms: float = Field(ge=0.0)
    reranking_ms: float = Field(default=0.0, ge=0.0)
    packaging_ms: float = Field(default=0.0, ge=0.0)


class RetrievalTrace(RetrievalModel):
    """Structured retrieval span for workflow, agent, and Langfuse integration."""

    trace_id: str
    retrieval_run_id: str
    workflow_id: str | None = None
    workflow_trace_id: str | None = None
    agent_run_id: str | None = None
    case_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    query_text: str
    query_length: int = Field(ge=0)
    retrieval_source: RetrievalBackend
    retrieval_mode: str
    fusion_strategy: str
    collection_name: str | None = None
    embedding_model: str | None = None
    retrieved_document_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    dense_result_count: int = Field(default=0, ge=0)
    bm25_result_count: int = Field(default=0, ge=0)
    reranked: bool = False
    filters_applied: bool = False
    retrieval_confidence: float = Field(ge=0.0, le=1.0)
    evidence_source_types: list[str] = Field(default_factory=list)
    latency: RetrievalLatencyBreakdown
    qdrant: QdrantSearchMetadata | None = None
    started_at: datetime
    completed_at: datetime
    status: str = "completed"


class RetrievalEvent(RetrievalModel):
    event_type: RetrievalEventType = RetrievalEventType.RETRIEVAL_COMPLETED
    trace: RetrievalTrace


class RetrievalFailureEvent(RetrievalModel):
    event_type: RetrievalEventType = RetrievalEventType.RETRIEVAL_FAILED
    retrieval_run_id: str
    trace_id: str | None = None
    workflow_id: str | None = None
    workflow_trace_id: str | None = None
    agent_run_id: str | None = None
    case_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    query_text: str | None = None
    retrieval_source: RetrievalBackend | None = None
    retrieval_mode: str | None = None
    collection_name: str | None = None
    error_type: str
    error_message: str
    latency_ms: float = Field(ge=0.0)
    started_at: datetime
    completed_at: datetime
    recoverable: bool = True
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RetrievalMetricsSink(Protocol):
    async def record_retrieval(self, event: RetrievalEvent) -> None:
        """Record a successful retrieval metrics event."""

    async def record_failure(self, event: RetrievalFailureEvent) -> None:
        """Record a failed retrieval metrics event."""


class NoopRetrievalMetricsSink:
    async def record_retrieval(self, event: RetrievalEvent) -> None:
        return None

    async def record_failure(self, event: RetrievalFailureEvent) -> None:
        return None


class InMemoryRetrievalMetricsSink:
    """Test double that captures retrieval metrics events."""

    def __init__(self) -> None:
        self.retrievals: list[RetrievalEvent] = []
        self.failures: list[RetrievalFailureEvent] = []

    async def record_retrieval(self, event: RetrievalEvent) -> None:
        self.retrievals.append(event)

    async def record_failure(self, event: RetrievalFailureEvent) -> None:
        self.failures.append(event)


class RetrievalObserver(Protocol):
    async def record_retrieval(self, event: RetrievalEvent) -> None:
        """Record a completed retrieval trace and metrics."""

    async def record_failure(self, event: RetrievalFailureEvent) -> None:
        """Record a retrieval failure event."""

    async def record_ingestion(
        self,
        *,
        source_uri: str,
        source_type: str,
        document_count: int,
        failure_count: int,
    ) -> None:
        """Record source ingestion metrics or traces."""

    async def record_indexing(
        self,
        *,
        collection_name: str,
        document_id: str,
        chunk_count: int,
        embedding_model: str,
    ) -> None:
        """Record indexing metrics or traces."""

    async def record_search(
        self,
        *,
        collection_name: str,
        query_length: int,
        result_count: int,
        embedding_model: str | None,
        filters_applied: bool,
        retrieval_mode: str = "dense",
        reranked: bool = False,
    ) -> None:
        """Backward-compatible search hook."""


class NoopRetrievalObserver:
    async def record_retrieval(self, event: RetrievalEvent) -> None:
        return None

    async def record_failure(self, event: RetrievalFailureEvent) -> None:
        return None

    async def record_ingestion(
        self,
        *,
        source_uri: str,
        source_type: str,
        document_count: int,
        failure_count: int,
    ) -> None:
        return None

    async def record_indexing(
        self,
        *,
        collection_name: str,
        document_id: str,
        chunk_count: int,
        embedding_model: str,
    ) -> None:
        return None

    async def record_search(
        self,
        *,
        collection_name: str,
        query_length: int,
        result_count: int,
        embedding_model: str | None,
        filters_applied: bool,
        retrieval_mode: str = "dense",
        reranked: bool = False,
    ) -> None:
        return None


class StructuredRetrievalObserver:
    """Emits structured logs and forwards retrieval events to a metrics sink."""

    def __init__(self, metrics_sink: RetrievalMetricsSink | None = None) -> None:
        self._metrics_sink = metrics_sink or NoopRetrievalMetricsSink()

    async def record_retrieval(self, event: RetrievalEvent) -> None:
        logger.info("retrieval_completed", **redacted_retrieval_trace(event.trace))
        await self._metrics_sink.record_retrieval(event)

    async def record_failure(self, event: RetrievalFailureEvent) -> None:
        logger.error(
            "retrieval_failed",
            retrieval_run_id=event.retrieval_run_id,
            trace_id=event.trace_id,
            workflow_id=event.workflow_id,
            workflow_trace_id=event.workflow_trace_id,
            agent_run_id=event.agent_run_id,
            case_id=event.case_id,
            retrieval_source=event.retrieval_source.value if event.retrieval_source else None,
            retrieval_mode=event.retrieval_mode,
            collection_name=event.collection_name,
            error_type=event.error_type,
            error_message=event.error_message,
            latency_ms=event.latency_ms,
            recoverable=event.recoverable,
        )
        await self._metrics_sink.record_failure(event)

    async def record_ingestion(
        self,
        *,
        source_uri: str,
        source_type: str,
        document_count: int,
        failure_count: int,
    ) -> None:
        logger.info(
            "retrieval_ingestion_completed",
            source_uri=source_uri,
            source_type=source_type,
            document_count=document_count,
            failure_count=failure_count,
        )

    async def record_indexing(
        self,
        *,
        collection_name: str,
        document_id: str,
        chunk_count: int,
        embedding_model: str,
    ) -> None:
        logger.info(
            "retrieval_indexing_completed",
            collection_name=collection_name,
            document_id=document_id,
            chunk_count=chunk_count,
            embedding_model=embedding_model,
        )

    async def record_search(
        self,
        *,
        collection_name: str,
        query_length: int,
        result_count: int,
        embedding_model: str | None,
        filters_applied: bool,
        retrieval_mode: str = "dense",
        reranked: bool = False,
    ) -> None:
        logger.info(
            "retrieval_search_recorded",
            collection_name=collection_name,
            query_length=query_length,
            result_count=result_count,
            embedding_model=embedding_model,
            filters_applied=filters_applied,
            retrieval_mode=retrieval_mode,
            reranked=reranked,
        )


def new_retrieval_run_id() -> str:
    return f"retrieval-run-{uuid4()}"


def redacted_retrieval_trace(trace: RetrievalTrace) -> dict[str, Any]:
    return {
        "retrieval_run_id": trace.retrieval_run_id,
        "trace_id": trace.trace_id,
        "workflow_id": trace.workflow_id,
        "workflow_trace_id": trace.workflow_trace_id,
        "agent_run_id": trace.agent_run_id,
        "case_id": trace.case_id,
        "query_length": trace.query_length,
        "query_preview": trace.query_text[:120],
        "retrieval_source": trace.retrieval_source.value,
        "retrieval_mode": trace.retrieval_mode,
        "fusion_strategy": trace.fusion_strategy,
        "collection_name": trace.collection_name,
        "embedding_model": trace.embedding_model,
        "retrieved_document_count": trace.retrieved_document_count,
        "candidate_count": trace.candidate_count,
        "dense_result_count": trace.dense_result_count,
        "bm25_result_count": trace.bm25_result_count,
        "reranked": trace.reranked,
        "filters_applied": trace.filters_applied,
        "retrieval_confidence": trace.retrieval_confidence,
        "evidence_source_types": trace.evidence_source_types,
        "latency_ms": trace.latency.total_ms,
        "retrieval_latency_ms": trace.latency.retrieval_ms,
        "reranking_latency_ms": trace.latency.reranking_ms,
        "packaging_latency_ms": trace.latency.packaging_ms,
        "qdrant": trace.qdrant.model_dump(mode="json") if trace.qdrant else None,
        "status": trace.status,
    }


def langfuse_retrieval_span(trace: RetrievalTrace) -> dict[str, Any]:
    """Langfuse-compatible nested span payload for retrieval."""
    return {
        "id": trace.retrieval_run_id,
        "name": "retrieval",
        "startTime": trace.started_at.isoformat(),
        "endTime": trace.completed_at.isoformat(),
        "metadata": {
            "retrieval_source": trace.retrieval_source.value,
            "retrieval_mode": trace.retrieval_mode,
            "fusion_strategy": trace.fusion_strategy,
            "collection_name": trace.collection_name,
            "embedding_model": trace.embedding_model,
            "retrieved_document_count": trace.retrieved_document_count,
            "candidate_count": trace.candidate_count,
            "retrieval_confidence": trace.retrieval_confidence,
            "evidence_source_types": trace.evidence_source_types,
            "reranked": trace.reranked,
            "filters_applied": trace.filters_applied,
            "qdrant": trace.qdrant.model_dump(mode="json") if trace.qdrant else None,
        },
        "input": {"query_length": trace.query_length},
        "output": {
            "retrieved_document_count": trace.retrieved_document_count,
            "retrieval_confidence": trace.retrieval_confidence,
        },
        "latencyMs": trace.latency.total_ms,
    }


def elapsed_ms(start: float) -> float:
    return max(0.0, (perf_counter() - start) * 1000)
