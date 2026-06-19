from __future__ import annotations

from clinical_ai_retrieval.attribution import SourceAttributionTracker
from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.contracts import Retriever
from clinical_ai_retrieval.observability import NoopRetrievalObserver, RetrievalObserver
from clinical_ai_retrieval.packaging import package_evidence
from clinical_ai_retrieval.retrievers.routing_retriever import RoutingRetriever
from clinical_ai_retrieval.rerankers import Reranker
from clinical_ai_retrieval.schemas import EvidencePackage, RetrievalQuery, RetrievalResult


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
        retriever_output = await self._retriever.retrieve_candidates(context)
        candidates = list(retriever_output.candidates)
        reranked = False
        query = context.query

        if query.rerank and self._reranker is not None and candidates:
            candidates = await self._reranker.rerank(
                query=query.query,
                results=candidates,
                limit=query.limit,
            )
            reranked = True
            candidates = attach_reliability_scores(candidates)
        else:
            candidates = candidates[: query.limit]

        await self._record_search(context, len(candidates), reranked=reranked)
        return package_evidence(
            query=query,
            results=candidates,
            backend=retriever_output.backend,
            dense_count=retriever_output.dense_result_count,
            bm25_count=retriever_output.bm25_result_count,
            reranked=reranked,
            attribution_tracker=self._attribution_tracker,
        )

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

    async def _record_search(
        self,
        context: RetrievalContext,
        result_count: int,
        *,
        reranked: bool = False,
    ) -> None:
        vector_store = self.vector_store
        collection_name = vector_store.collection_name if vector_store is not None else "inline_corpus"
        await self._observer.record_search(
            collection_name=collection_name,
            query_length=len(context.query.query),
            result_count=result_count,
            embedding_model=self.embedding_model_name,
            filters_applied=context.query.filters != type(context.query.filters)(),
            retrieval_mode=context.query.mode.value,
            reranked=reranked,
        )
