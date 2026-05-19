from typing import Protocol


class RetrievalObserver(Protocol):
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
    ) -> None:
        """Record retrieval metrics or traces."""


class NoopRetrievalObserver:
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
    ) -> None:
        return None
