"""Evidence retrieval and vector indexing package."""

from clinical_ai_retrieval.attribution import SourceAttributionTracker
from clinical_ai_retrieval.embeddings import (
    EmbeddingProvider,
    HostedEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from clinical_ai_retrieval.schemas import (
    EvidencePackage,
    EvidenceDocument,
    EvidenceMetadata,
    EvidenceSourceType,
    IngestionResult,
    MetadataFilter,
    RetrievalQuery,
    RetrievalResult,
)

__all__ = [
    "EmbeddingProvider",
    "EvidencePackage",
    "EvidenceDocument",
    "EvidenceMetadata",
    "EvidenceSourceType",
    "HostedEmbeddingProvider",
    "IngestionResult",
    "MetadataFilter",
    "RetrievalQuery",
    "RetrievalResult",
    "SentenceTransformerEmbeddingProvider",
    "SourceAttributionTracker",
]
