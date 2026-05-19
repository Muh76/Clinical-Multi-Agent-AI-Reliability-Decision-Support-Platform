"""Evidence retrieval package."""
"""Evidence retrieval and vector indexing package."""

from clinical_ai_retrieval.embeddings import (
    EmbeddingProvider,
    HostedEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from clinical_ai_retrieval.schemas import (
    EvidenceDocument,
    EvidenceMetadata,
    MetadataFilter,
    RetrievalQuery,
    RetrievalResult,
)

__all__ = [
    "EmbeddingProvider",
    "EvidenceDocument",
    "EvidenceMetadata",
    "HostedEmbeddingProvider",
    "MetadataFilter",
    "RetrievalQuery",
    "RetrievalResult",
    "SentenceTransformerEmbeddingProvider",
]
