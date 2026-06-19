from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from clinical_ai_retrieval.attribution import SourceAttributionTracker
from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.contracts import Retriever
from clinical_ai_retrieval.observability import (
    NoopRetrievalObserver,
    RetrievalEvent,
    RetrievalFailureEvent,
    RetrievalLatencyBreakdown,
    RetrievalObserver,
    RetrievalTrace,
    elapsed_ms,
    new_retrieval_run_id,
)
from clinical_ai_retrieval.packaging import package_evidence
from clinical_ai_retrieval.retrievers.routing_retriever import RoutingRetriever
from clinical_ai_retrieval.retrievers.types import RetrieverOutput
from clinical_ai_retrieval.rerankers import Reranker
from clinical_ai_retrieval.schemas import EvidencePackage, RetrievalQuery, RetrievalResult
from clinical_ai_retrieval.scoring import attach_reliability_scores


class RetrievalService:
    """Authoritative retrieval entry point: retriever → rerank → score → package."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        reranker: Reranker | None = None,
        observer: RetrievalObserver | None = None,
        attribution_tracker: SourceAttributionTracker | None = None,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._observer = observer or NoopRetrievalObserver()
        self._attribution_tracker = attribution_tracker or SourceAttributionTracker()
        self.last_trace: RetrievalTrace | None = None
        self.last_failure: RetrievalFailureEvent | None = None

    @property
    def vector_store(self):
        if isinstance(self._retriever, RoutingRetriever):
            qdrant = self._retriever.qdrant_retriever
            if qdrant is not None:
                return getattr(qdrant, "vector_store", None)
        return getattr(self._retriever, "vector_store", None)

    @property
    def embedding_model_name(self) -> str | None:
        if isinstance(self._retriever, RoutingRetriever):
            qdrant = self._retriever.qdrant_retriever
            if qdrant is not None:
                provider = getattr(qdrant, "_embedding_provider", None)
                if provider is not None:
                    return provider.model_name
        provider = getattr(self._retriever, "_embedding_provider", None)
        if provider is not None:
            return provider.model_name
        return None

    async def retrieve_evidence(self, context: RetrievalContext) -> EvidencePackage:
        started_at = datetime.now(UTC)
        run_started = perf_counter()
        retrieval_run_id = new_retrieval_run_id()
        query = context.query
        self.last_failure = None

        try:
            retrieval_started = perf_counter()
            retriever_output = await self._retriever.retrieve_candidates(context)
            retrieval_ms = retriever_output.retrieval_latency_ms or elapsed_ms(retrieval_started)

            candidates = list(retriever_output.candidates)
            candidate_count = len(candidates)
            reranked = False
            reranking_ms = 0.0

            if query.rerank and self._reranker is not None and candidates:
                rerank_started = perf_counter()
                candidates = await self._reranker.rerank(
                    query=query.query,
                    results=candidates,
                    limit=query.limit,
                )
                reranked = True
                reranking_ms = elapsed_ms(rerank_started)
                candidates = attach_reliability_scores(candidates)
            else:
                candidates = candidates[: query.limit]

            packaging_started = perf_counter()
            package = package_evidence(
                query=query,
                results=candidates,
                backend=retriever_output.backend,
                dense_count=retriever_output.dense_result_count,
                bm25_count=retriever_output.bm25_result_count,
                reranked=reranked,
                attribution_tracker=self._attribution_tracker,
            )
            packaging_ms = elapsed_ms(packaging_started)
            total_ms = elapsed_ms(run_started)

            trace = self._build_trace(
                context=context,
                retriever_output=retriever_output,
                package=package,
                retrieval_run_id=retrieval_run_id,
                started_at=started_at,
                retrieval_ms=retrieval_ms,
                reranking_ms=reranking_ms,
                packaging_ms=packaging_ms,
                total_ms=total_ms,
                candidate_count=candidate_count,
                reranked=reranked,
            )
            self.last_trace = trace
            await self._emit_success(trace)
            return package.model_copy(update={"retrieval_trace_id": trace.retrieval_run_id})
        except Exception as exc:
            failure = RetrievalFailureEvent(
                retrieval_run_id=retrieval_run_id,
                trace_id=context.workflow_trace_id,
                workflow_id=context.workflow_id,
                workflow_trace_id=context.workflow_trace_id,
                agent_run_id=context.agent_run_id,
                case_id=context.case_id,
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                query_text=query.query,
                retrieval_mode=query.mode.value,
                collection_name=self._collection_name(),
                error_type=type(exc).__name__,
                error_message=str(exc),
                latency_ms=elapsed_ms(run_started),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            self.last_failure = failure
            await self._observer.record_failure(failure)
            raise

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        package = await self.retrieve_evidence(RetrievalContext(query=query))
        return [
            RetrievalResult(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                score=item.score,
                text=item.text,
                metadata=item.metadata,
                confidence_score=item.confidence_score,
                source_reliability_score=item.source_reliability_score,
            )
            for item in package.evidence
        ]

    def _build_trace(
        self,
        *,
        context: RetrievalContext,
        retriever_output: RetrieverOutput,
        package: EvidencePackage,
        retrieval_run_id: str,
        started_at: datetime,
        retrieval_ms: float,
        reranking_ms: float,
        packaging_ms: float,
        total_ms: float,
        candidate_count: int,
        reranked: bool,
    ) -> RetrievalTrace:
        query = context.query
        source_types = sorted(
            {item.metadata.source_type.value for item in package.evidence}
        )
        return RetrievalTrace(
            trace_id=context.workflow_trace_id or retrieval_run_id,
            retrieval_run_id=retrieval_run_id,
            workflow_id=context.workflow_id,
            workflow_trace_id=context.workflow_trace_id,
            agent_run_id=context.agent_run_id,
            case_id=context.case_id,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            query_text=query.query,
            query_length=len(query.query),
            retrieval_source=retriever_output.backend,
            retrieval_mode=query.mode.value,
            fusion_strategy=query.fusion_strategy.value,
            collection_name=self._collection_name(),
            embedding_model=self.embedding_model_name,
            retrieved_document_count=len(package.evidence),
            candidate_count=candidate_count,
            dense_result_count=retriever_output.dense_result_count,
            bm25_result_count=retriever_output.bm25_result_count,
            reranked=reranked,
            filters_applied=query.filters != type(query.filters)(),
            retrieval_confidence=package.confidence_score,
            evidence_source_types=source_types,
            latency=RetrievalLatencyBreakdown(
                total_ms=total_ms,
                retrieval_ms=retrieval_ms,
                reranking_ms=reranking_ms,
                packaging_ms=packaging_ms,
            ),
            qdrant=retriever_output.qdrant_metadata,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )

    def _collection_name(self) -> str | None:
        vector_store = self.vector_store
        if vector_store is not None:
            collection_name = getattr(vector_store, "collection_name", None)
            if isinstance(collection_name, str):
                return collection_name
        return "inline_corpus"

    async def _emit_success(self, trace: RetrievalTrace) -> None:
        await self._observer.record_retrieval(RetrievalEvent(trace=trace))
        await self._observer.record_search(
            collection_name=trace.collection_name or "inline_corpus",
            query_length=trace.query_length,
            result_count=trace.retrieved_document_count,
            embedding_model=trace.embedding_model,
            filters_applied=trace.filters_applied,
            retrieval_mode=trace.retrieval_mode,
            reranked=trace.reranked,
        )
