from __future__ import annotations

from clinical_ai_retrieval.bm25 import BM25Retriever
from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.retrievers.types import RetrieverOutput
from clinical_ai_retrieval.schemas import RetrievalBackend, RetrievalMode, RetrievalResult
from clinical_ai_retrieval.scoring import attach_reliability_scores


class LocalCorpusRetriever:
    backend = RetrievalBackend.LOCAL_CORPUS

    async def retrieve_candidates(self, context: RetrievalContext) -> RetrieverOutput:
        query = context.query
        if not context.inline_corpus:
            return RetrieverOutput(
                candidates=[],
                backend=self.backend,
                bm25_result_count=0,
            )

        bm25 = BM25Retriever()
        bm25.index_documents(context.inline_corpus)
        if query.mode == RetrievalMode.DENSE:
            candidates = _all_filtered_documents(context)
            bm25_count = 0
        else:
            candidates = await bm25.retrieve(
                query=query.query,
                limit=query.candidate_limit,
                filters=query.filters,
            )
            if not candidates and not query.query.strip():
                candidates = _all_filtered_documents(context)
            bm25_count = len(candidates)

        return RetrieverOutput(
            candidates=attach_reliability_scores(candidates),
            backend=self.backend,
            bm25_result_count=bm25_count,
        )


def _all_filtered_documents(context: RetrievalContext) -> list[RetrievalResult]:
    from clinical_ai_retrieval.bm25 import metadata_matches

    results: list[RetrievalResult] = []
    for document in context.inline_corpus:
        if not metadata_matches(document, context.query.filters):
            continue
        results.append(
            RetrievalResult(
                chunk_id=f"{document.document_id}:0",
                document_id=document.document_id,
                score=0.5,
                text=document.text,
                metadata=document.metadata,
                lexical_score=0.5,
            )
        )
    return results[: context.query.candidate_limit]
