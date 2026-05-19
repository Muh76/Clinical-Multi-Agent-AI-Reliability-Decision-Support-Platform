from typing import Protocol

from clinical_ai_retrieval.embeddings import EmbeddingProvider
from clinical_ai_retrieval.observability import NoopRetrievalObserver, RetrievalObserver
from clinical_ai_retrieval.qdrant import QdrantVectorStore
from clinical_ai_retrieval.schemas import RetrievalQuery, RetrievalResult


class Reranker(Protocol):
    async def rerank(
        self,
        *,
        query: str,
        results: list[RetrievalResult],
        limit: int,
    ) -> list[RetrievalResult]:
        """Reorder initial vector hits with a cross-encoder or hosted reranker."""


class VectorRetrievalService:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
        reranker: Reranker | None = None,
        observer: RetrievalObserver | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.reranker = reranker
        self.observer = observer or NoopRetrievalObserver()

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        await self.vector_store.ensure_collection()
        query_vector = await self.embedding_provider.embed_query(query.query)
        results = await self.vector_store.search(
            query_vector=query_vector,
            limit=query.limit,
            filters=query.filters,
            score_threshold=query.score_threshold,
            with_payload=query.include_payload,
            with_vectors=query.include_vectors,
        )
        if self.reranker is None:
            await self._record_search(query, len(results))
            return results
        reranked_results = await self.reranker.rerank(
            query=query.query,
            results=results,
            limit=query.limit,
        )
        await self._record_search(query, len(reranked_results))
        return reranked_results

    async def _record_search(self, query: RetrievalQuery, result_count: int) -> None:
        await self.observer.record_search(
            collection_name=self.vector_store.collection_name,
            query_length=len(query.query),
            result_count=result_count,
            embedding_model=self.embedding_provider.model_name,
            filters_applied=query.filters != type(query.filters)(),
        )
