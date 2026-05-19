from uuid import NAMESPACE_URL, uuid5

from clinical_ai_retrieval.chunking import TextChunker
from clinical_ai_retrieval.embeddings import EmbeddingProvider
from clinical_ai_retrieval.observability import NoopRetrievalObserver, RetrievalObserver
from clinical_ai_retrieval.qdrant import QdrantVectorStore
from clinical_ai_retrieval.schemas import (
    EvidenceDocument,
    IndexingResult,
    IndexingStatus,
    VectorRecord,
)


class VectorIndexingPipeline:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
        chunker: TextChunker | None = None,
        embedding_batch_size: int = 32,
        observer: RetrievalObserver | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.chunker = chunker or TextChunker()
        self.embedding_batch_size = embedding_batch_size
        self.observer = observer or NoopRetrievalObserver()

    async def index_document(self, document: EvidenceDocument) -> IndexingResult:
        chunks = self.chunker.chunk_document(document)
        if not chunks:
            return IndexingResult(
                document_id=document.document_id,
                status=IndexingStatus.SKIPPED,
                chunk_count=0,
                collection_name=self.vector_store.collection_name,
            )

        await self.vector_store.ensure_collection()
        records: list[VectorRecord] = []
        for start in range(0, len(chunks), self.embedding_batch_size):
            batch = chunks[start : start + self.embedding_batch_size]
            vectors = await self.embedding_provider.embed_texts([chunk.text for chunk in batch])
            records.extend(
                VectorRecord(
                    id=stable_chunk_record_id(chunk.chunk_id),
                    vector=vector,
                    chunk=chunk,
                )
                for chunk, vector in zip(batch, vectors, strict=True)
            )
        await self.vector_store.upsert(records)
        await self.observer.record_indexing(
            collection_name=self.vector_store.collection_name,
            document_id=document.document_id,
            chunk_count=len(chunks),
            embedding_model=self.embedding_provider.model_name,
        )
        return IndexingResult(
            document_id=document.document_id,
            status=IndexingStatus.UPDATED,
            chunk_count=len(chunks),
            collection_name=self.vector_store.collection_name,
        )

    async def index_documents(self, documents: list[EvidenceDocument]) -> list[IndexingResult]:
        return [await self.index_document(document) for document in documents]


def stable_chunk_record_id(chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"clinical-ai-retrieval:{chunk_id}"))
