from typing import Protocol


class RetrievalObserver(Protocol):
    async def record_ingestion(
        self,
        *,
        source_uri: str,
        source_type: str,
        document_count: int,
        failure_count: int,
    ) -> None:
        """Record source ingestion metrics or traces."""

    async def record_indexing(
        self,
        *,
        collection_name: str,
        document_id: str,
        chunk_count: int,
        embedding_model: str,
    ) -> None:
        """Record indexing metrics or traces."""

    async def record_search(
        self,
        *,
        collection_name: str,
        query_length: int,
        result_count: int,
        embedding_model: str,
        filters_applied: bool,
        retrieval_mode: str = "dense",
        reranked: bool = False,
    ) -> None:
        """Record retrieval metrics or traces."""


class NoopRetrievalObserver:
    async def record_ingestion(
        self,
        *,
        source_uri: str,
        source_type: str,
        document_count: int,
        failure_count: int,
    ) -> None:
        return None

    async def record_indexing(
        self,
        *,
        collection_name: str,
        document_id: str,
        chunk_count: int,
        embedding_model: str,
    ) -> None:
        return None

    async def record_search(
        self,
        *,
        collection_name: str,
        query_length: int,
        result_count: int,
        embedding_model: str,
        filters_applied: bool,
        retrieval_mode: str = "dense",
        reranked: bool = False,
    ) -> None:
        return None
