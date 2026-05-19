from __future__ import annotations

import asyncio
from typing import Protocol

from clinical_ai_retrieval.schemas import RetrievalResult
from clinical_ai_retrieval.scoring import attach_reliability_scores


class Reranker(Protocol):
    async def rerank(
        self,
        *,
        query: str,
        results: list[RetrievalResult],
        limit: int,
    ) -> list[RetrievalResult]:
        """Reorder candidate results with a more precise relevance model."""


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        *,
        batch_size: int = 16,
    ) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self.batch_size = batch_size
        self._model = CrossEncoder(model_name)

    async def rerank(
        self,
        *,
        query: str,
        results: list[RetrievalResult],
        limit: int,
    ) -> list[RetrievalResult]:
        if not results:
            return []
        scores = await asyncio.to_thread(self._predict, query, results)
        reranked = [
            result.model_copy(
                update={
                    "rerank_score": float(score),
                    "score": float(score),
                }
            )
            for result, score in zip(results, scores, strict=True)
        ]
        ranked = sorted(reranked, key=lambda result: result.rerank_score or 0.0, reverse=True)
        return attach_reliability_scores(ranked[:limit])

    def _predict(self, query: str, results: list[RetrievalResult]) -> list[float]:
        pairs = [(query, result.text) for result in results]
        scores = self._model.predict(pairs, batch_size=self.batch_size)
        return [float(score) for score in scores]
