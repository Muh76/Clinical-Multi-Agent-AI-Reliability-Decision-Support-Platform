from __future__ import annotations

from time import perf_counter

from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.embeddings import EmbeddingProvider
from clinical_ai_retrieval.fusion import fuse_results
from clinical_ai_retrieval.observability import QdrantSearchMetadata, elapsed_ms
from clinical_ai_retrieval.qdrant import QdrantVectorStore
from clinical_ai_retrieval.retrievers.types import RetrieverOutput
from clinical_ai_retrieval.schemas import RetrievalBackend, RetrievalMode, RetrievalQuery, RetrievalResult
from clinical_ai_retrieval.scoring import attach_reliability_scores


class QdrantRetriever:
    backend = RetrievalBackend.QDRANT

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    @property
    def vector_store(self) -> QdrantVectorStore:
        return self._vector_store

    async def retrieve_candidates(self, context: RetrievalContext) -> RetrieverOutput:
        started = perf_counter()
        query = context.query
        dense_results: list[RetrievalResult] = []
        qdrant_metadata: QdrantSearchMetadata | None = None
        if query.mode in {RetrievalMode.DENSE, RetrievalMode.HYBRID}:
            dense_results, qdrant_metadata = await self._dense_retrieve(query)

        candidates = dense_results[: query.candidate_limit]
        if query.mode == RetrievalMode.HYBRID and dense_results:
            candidates = fuse_results(
                dense_results=dense_results,
                bm25_results=[],
                dense_weight=query.dense_weight,
                bm25_weight=query.bm25_weight,
                strategy=query.fusion_strategy,
                limit=query.candidate_limit,
            )

        return RetrieverOutput(
            candidates=attach_reliability_scores(candidates),
            backend=self.backend,
            dense_result_count=len(dense_results),
            retrieval_latency_ms=elapsed_ms(started),
            qdrant_metadata=qdrant_metadata,
        )

    async def _dense_retrieve(
        self,
        query: RetrievalQuery,
    ) -> tuple[list[RetrievalResult], QdrantSearchMetadata]:
        await self._vector_store.ensure_collection()
        embed_started = perf_counter()
        query_vector = await self._embedding_provider.embed_query(query.query)
        embedding_latency_ms = elapsed_ms(embed_started)
        search_started = perf_counter()
        results = await self._vector_store.search(
            query_vector=query_vector,
            limit=query.candidate_limit,
            filters=query.filters,
            score_threshold=query.score_threshold,
            with_payload=query.include_payload,
            with_vectors=query.include_vectors,
        )
        search_latency_ms = elapsed_ms(search_started)
        metadata = QdrantSearchMetadata(
            collection_name=self._vector_store.collection_name,
            vector_size=self._vector_store.vector_size,
            search_limit=query.candidate_limit,
            score_threshold=query.score_threshold,
            filters_applied=query.filters != type(query.filters)(),
            with_payload=query.include_payload,
            with_vectors=query.include_vectors,
            embedding_model=self._embedding_provider.model_name,
            embedding_latency_ms=embedding_latency_ms,
            search_latency_ms=search_latency_ms,
            points_returned=len(results),
        )
        return [
            result.model_copy(update={"dense_score": result.score}) for result in results
        ], metadata
