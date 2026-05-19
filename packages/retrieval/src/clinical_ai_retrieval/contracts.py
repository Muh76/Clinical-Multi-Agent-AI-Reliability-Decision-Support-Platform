from typing import Protocol

from clinical_ai_retrieval.schemas import (
    EvidenceDocument,
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


class EvidenceIndexer(Protocol):
    async def index_document(self, document: EvidenceDocument) -> IndexingResult:
        """Chunk, embed, and index one evidence document."""
