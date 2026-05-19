from clinical_ai_retrieval.attribution import SourceAttributionTracker
from clinical_ai_retrieval.bm25 import BM25Retriever
from clinical_ai_retrieval.embeddings import EmbeddingProvider
from clinical_ai_retrieval.fusion import fuse_results
from clinical_ai_retrieval.observability import NoopRetrievalObserver, RetrievalObserver
from clinical_ai_retrieval.qdrant import QdrantVectorStore
from clinical_ai_retrieval.rerankers import Reranker
from clinical_ai_retrieval.schemas import (
    EvidencePackage,
    RetrievalDiagnostics,
    RetrievalEvidenceItem,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
)
from clinical_ai_retrieval.scoring import attach_reliability_scores


class VectorRetrievalService:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
        bm25_retriever: BM25Retriever | None = None,
        reranker: Reranker | None = None,
        observer: RetrievalObserver | None = None,
        attribution_tracker: SourceAttributionTracker | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.bm25_retriever = bm25_retriever
        self.reranker = reranker
        self.observer = observer or NoopRetrievalObserver()
        self.attribution_tracker = attribution_tracker or SourceAttributionTracker()

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        package = await self.retrieve_evidence(query)
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

    async def retrieve_evidence(self, query: RetrievalQuery) -> EvidencePackage:
        dense_results: list[RetrievalResult] = []
        bm25_results: list[RetrievalResult] = []
        if query.mode in {RetrievalMode.DENSE, RetrievalMode.HYBRID}:
            dense_results = await self._dense_retrieve(query)
        if query.mode in {RetrievalMode.BM25, RetrievalMode.HYBRID} and self.bm25_retriever:
            bm25_results = await self.bm25_retriever.retrieve(
                query=query.query,
                limit=query.candidate_limit,
                filters=query.filters,
            )

        candidates = self._candidate_results(query, dense_results, bm25_results)
        reranked = False
        if query.rerank and self.reranker is not None:
            candidates = await self.reranker.rerank(
                query=query.query,
                results=candidates,
                limit=query.limit,
            )
            reranked = True
        else:
            candidates = candidates[: query.limit]

        candidates = attach_reliability_scores(candidates)
        await self._record_search(query, len(candidates), reranked=reranked)
        return self._package_evidence(
            query=query,
            results=candidates,
            dense_count=len(dense_results),
            bm25_count=len(bm25_results),
            reranked=reranked,
        )

    async def _dense_retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        await self.vector_store.ensure_collection()
        query_vector = await self.embedding_provider.embed_query(query.query)
        results = await self.vector_store.search(
            query_vector=query_vector,
            limit=query.candidate_limit,
            filters=query.filters,
            score_threshold=query.score_threshold,
            with_payload=query.include_payload,
            with_vectors=query.include_vectors,
        )
        return attach_reliability_scores(
            [result.model_copy(update={"dense_score": result.score}) for result in results]
        )

    def _candidate_results(
        self,
        query: RetrievalQuery,
        dense_results: list[RetrievalResult],
        bm25_results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        if query.mode == RetrievalMode.DENSE:
            return dense_results[: query.candidate_limit]
        if query.mode == RetrievalMode.BM25:
            return bm25_results[: query.candidate_limit]
        return fuse_results(
            dense_results=dense_results,
            bm25_results=bm25_results,
            dense_weight=query.dense_weight,
            bm25_weight=query.bm25_weight,
            strategy=query.fusion_strategy,
            limit=query.candidate_limit,
        )

    def _package_evidence(
        self,
        *,
        query: RetrievalQuery,
        results: list[RetrievalResult],
        dense_count: int,
        bm25_count: int,
        reranked: bool,
    ) -> EvidencePackage:
        citations = self.attribution_tracker.citations_from_results(results)
        evidence = [
            RetrievalEvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=result.text,
                citation=citation,
                metadata=result.metadata,
                score=result.score,
                confidence_score=result.confidence_score,
                source_reliability_score=result.source_reliability_score,
                rank=rank,
                scoring_components=scoring_components(result),
            )
            for rank, (result, citation) in enumerate(zip(results, citations, strict=True), start=1)
        ]
        diagnostics = RetrievalDiagnostics(
            mode=query.mode,
            fusion_strategy=query.fusion_strategy,
            dense_result_count=dense_count,
            bm25_result_count=bm25_count,
            reranked=reranked,
            filters_applied=query.filters != type(query.filters)(),
            reliability_notes=reliability_notes(results),
        )
        package_confidence = (
            sum(item.confidence_score for item in evidence) / len(evidence)
            if evidence
            else 0.0
        )
        return EvidencePackage(
            query=query.query,
            evidence=evidence,
            citations=citations,
            diagnostics=diagnostics,
            confidence_score=package_confidence,
        )

    async def _record_search(
        self,
        query: RetrievalQuery,
        result_count: int,
        *,
        reranked: bool = False,
    ) -> None:
        await self.observer.record_search(
            collection_name=self.vector_store.collection_name,
            query_length=len(query.query),
            result_count=result_count,
            embedding_model=self.embedding_provider.model_name,
            filters_applied=query.filters != type(query.filters)(),
            retrieval_mode=query.mode.value,
            reranked=reranked,
        )


def scoring_components(result: RetrievalResult) -> dict[str, float]:
    components = {
        "final": result.score,
        "confidence": result.confidence_score,
        "source_reliability": result.source_reliability_score,
    }
    if result.dense_score is not None:
        components["dense"] = result.dense_score
    if result.lexical_score is not None:
        components["bm25"] = result.lexical_score
    if result.rerank_score is not None:
        components["rerank"] = result.rerank_score
    return components


def reliability_notes(results: list[RetrievalResult]) -> list[str]:
    notes: list[str] = []
    if not results:
        return ["No evidence chunks were retrieved for this query."]
    if all(result.metadata.source_type.value == "synthetic_protocol" for result in results):
        notes.append(
            "Only synthetic protocol evidence was retrieved; avoid treating it as clinical authority."
        )
    if any(result.confidence_score < 0.35 for result in results):
        notes.append("Some retrieved chunks have low confidence and should be reviewed before use.")
    if len({result.metadata.source_type for result in results}) > 1:
        notes.append(
            "Evidence package includes multiple source types; downstream answers should cite source class."
        )
    return notes
