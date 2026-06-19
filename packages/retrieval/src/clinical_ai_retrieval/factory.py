from pydantic import SecretStr

from clinical_ai_retrieval.embeddings import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from clinical_ai_retrieval.indexing import VectorIndexingPipeline
from clinical_ai_retrieval.ingestion import (
    KnowledgeIngestionPipeline,
    default_loaders,
    default_processors,
)
from clinical_ai_retrieval.qdrant import QdrantVectorStore
from clinical_ai_retrieval.observability import StructuredRetrievalObserver
from clinical_ai_retrieval.rerankers import CrossEncoderReranker
from clinical_ai_retrieval.retrieval_service import RetrievalService
from clinical_ai_retrieval.retrievers import LocalCorpusRetriever, QdrantRetriever, RoutingRetriever


def build_sentence_transformer_provider(
    model_name: str | None = None,
) -> SentenceTransformerEmbeddingProvider:
    return SentenceTransformerEmbeddingProvider(
        model_name or "sentence-transformers/all-MiniLM-L6-v2"
    )


def build_qdrant_store(
    *,
    url: str,
    collection_prefix: str,
    embedding_provider: EmbeddingProvider,
    api_key: SecretStr | None = None,
    collection_suffix: str = "evidence",
) -> QdrantVectorStore:
    collection_name = f"{collection_prefix}_{collection_suffix}_{embedding_provider.dimension}"
    return QdrantVectorStore(
        url=url,
        api_key=api_key,
        collection_name=collection_name,
        vector_size=embedding_provider.dimension,
    )


def build_local_retrieval_service() -> RetrievalService:
    return RetrievalService(
        retriever=LocalCorpusRetriever(),
        observer=StructuredRetrievalObserver(),
    )


def build_retrieval_service(
    *,
    url: str | None = None,
    collection_prefix: str = "clinical_ai",
    model_name: str | None = None,
    api_key: SecretStr | None = None,
    enable_reranker: bool = False,
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> RetrievalService:
    local = LocalCorpusRetriever()
    qdrant_retriever: QdrantRetriever | None = None
    if url is not None:
        embedding_provider = build_sentence_transformer_provider(model_name)
        vector_store = build_qdrant_store(
            url=url,
            api_key=api_key,
            collection_prefix=collection_prefix,
            embedding_provider=embedding_provider,
        )
        qdrant_retriever = QdrantRetriever(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
    retriever = RoutingRetriever(local=local, qdrant=qdrant_retriever)
    return RetrievalService(
        retriever=retriever,
        reranker=CrossEncoderReranker(reranker_model_name) if enable_reranker else None,
        observer=StructuredRetrievalObserver(),
    )


def build_indexing_pipeline(
    *,
    url: str,
    collection_prefix: str,
    model_name: str | None = None,
    api_key: SecretStr | None = None,
) -> VectorIndexingPipeline:
    embedding_provider = build_sentence_transformer_provider(model_name)
    vector_store = build_qdrant_store(
        url=url,
        api_key=api_key,
        collection_prefix=collection_prefix,
        embedding_provider=embedding_provider,
    )
    return VectorIndexingPipeline(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )


def build_ingestion_pipeline(
    *,
    url: str,
    collection_prefix: str,
    model_name: str | None = None,
    api_key: SecretStr | None = None,
) -> KnowledgeIngestionPipeline:
    return KnowledgeIngestionPipeline(
        loaders=default_loaders(),
        processors=default_processors(),
        indexer=build_indexing_pipeline(
            url=url,
            api_key=api_key,
            collection_prefix=collection_prefix,
            model_name=model_name,
        ),
    )
