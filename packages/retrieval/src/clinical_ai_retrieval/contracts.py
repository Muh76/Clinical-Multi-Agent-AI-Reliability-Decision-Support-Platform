from typing import Protocol

from clinical_ai_retrieval.schemas import (
    EvidenceDocument,
    EvidencePackage,
    EvidenceSourceType,
    IngestionResult,
    IndexingResult,
    RetrievalQuery,
    RetrievalResult,
)


class EvidenceRetriever(Protocol):
    async def retrieve(self, query: str, limit: int = 10) -> list[str]:
        """Retrieve evidence references relevant to the query."""


class VectorEvidenceRetriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        """Retrieve ranked evidence chunks with provenance and metadata."""


class EvidencePackager(Protocol):
    async def retrieve_evidence(self, query: RetrievalQuery) -> EvidencePackage:
        """Retrieve, score, rerank, attribute, and package clinical evidence."""


class EvidenceIndexer(Protocol):
    async def index_document(self, document: EvidenceDocument) -> IndexingResult:
        """Chunk, embed, and index one evidence document."""


class KnowledgeIngestor(Protocol):
    async def ingest(self, source_uri: str, source_type: EvidenceSourceType) -> IngestionResult:
        """Load, process, embed, index, and attribute a knowledge source."""
