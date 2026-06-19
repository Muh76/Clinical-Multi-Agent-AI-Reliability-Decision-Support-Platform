from __future__ import annotations

from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.retrievers.local_corpus_retriever import LocalCorpusRetriever
from clinical_ai_retrieval.retrievers.qdrant_retriever import QdrantRetriever
from clinical_ai_retrieval.retrievers.types import RetrieverOutput


class RoutingRetriever:
    """Selects local corpus or Qdrant based on request context."""

    def __init__(
        self,
        *,
        local: LocalCorpusRetriever,
        qdrant: QdrantRetriever | None = None,
    ) -> None:
        self._local = local
        self._qdrant = qdrant

    @property
    def qdrant_retriever(self) -> QdrantRetriever | None:
        return self._qdrant

    async def retrieve_candidates(self, context: RetrievalContext) -> RetrieverOutput:
        if context.has_inline_corpus:
            return await self._local.retrieve_candidates(context)
        if self._qdrant is not None:
            return await self._qdrant.retrieve_candidates(context)
        return await self._local.retrieve_candidates(context)
