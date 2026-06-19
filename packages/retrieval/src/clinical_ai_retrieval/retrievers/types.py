from __future__ import annotations

from dataclasses import dataclass

from clinical_ai_retrieval.observability import QdrantSearchMetadata
from clinical_ai_retrieval.schemas import RetrievalBackend, RetrievalResult


@dataclass(frozen=True, slots=True)
class RetrieverOutput:
    candidates: list[RetrievalResult]
    backend: RetrievalBackend
    dense_result_count: int = 0
    bm25_result_count: int = 0
    retrieval_latency_ms: float = 0.0
    qdrant_metadata: QdrantSearchMetadata | None = None
