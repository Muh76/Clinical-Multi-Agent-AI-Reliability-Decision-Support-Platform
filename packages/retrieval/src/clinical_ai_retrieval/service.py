"""Backward-compatible vector retrieval module.

`VectorRetrievalService` is retained as an alias for `RetrievalService`.
New code should import `RetrievalService` from `clinical_ai_retrieval.retrieval_service`.
"""

from clinical_ai_retrieval.packaging import reliability_notes, scoring_components
from clinical_ai_retrieval.retrieval_service import RetrievalService

VectorRetrievalService = RetrievalService

__all__ = ["RetrievalService", "VectorRetrievalService", "reliability_notes", "scoring_components"]
