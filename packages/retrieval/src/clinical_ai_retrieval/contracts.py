from typing import Protocol


class EvidenceRetriever(Protocol):
    async def retrieve(self, query: str, limit: int = 10) -> list[str]:
        """Retrieve evidence references relevant to the query."""

