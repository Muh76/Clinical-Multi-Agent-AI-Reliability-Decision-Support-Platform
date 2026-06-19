"""Evidence retrieval and vector indexing package."""

from clinical_ai_retrieval.attribution import SourceAttributionTracker
from clinical_ai_retrieval.context import RetrievalContext, build_retrieval_context
from clinical_ai_retrieval.embeddings import (
    EmbeddingProvider,
    HostedEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from clinical_ai_retrieval.factory import build_local_retrieval_service, build_retrieval_service
from clinical_ai_retrieval.observability import (
    InMemoryRetrievalMetricsSink,
    QdrantSearchMetadata,
    RetrievalEvent,
    RetrievalFailureEvent,
    RetrievalTrace,
    StructuredRetrievalObserver,
    langfuse_retrieval_span,
)
from clinical_ai_retrieval.retrieval_service import RetrievalService
from clinical_ai_retrieval.schemas import (
    EvidencePackage,
    EvidenceDocument,
    EvidenceMetadata,
    EvidenceSourceType,
    IngestionResult,
    MetadataFilter,
    RetrievalBackend,
    RetrievalQuery,
    RetrievalResult,
)
from clinical_ai_retrieval.service import VectorRetrievalService

__all__ = [
    "EmbeddingProvider",
    "EvidencePackage",
    "EvidenceDocument",
    "EvidenceMetadata",
    "EvidenceSourceType",
    "HostedEmbeddingProvider",
    "IngestionResult",
    "InMemoryRetrievalMetricsSink",
    "MetadataFilter",
    "QdrantSearchMetadata",
    "RetrievalBackend",
    "RetrievalContext",
    "RetrievalEvent",
    "RetrievalFailureEvent",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalService",
    "RetrievalTrace",
    "SentenceTransformerEmbeddingProvider",
    "SourceAttributionTracker",
    "StructuredRetrievalObserver",
    "VectorRetrievalService",
    "build_local_retrieval_service",
    "build_retrieval_context",
    "build_retrieval_service",
    "langfuse_retrieval_span",
]
