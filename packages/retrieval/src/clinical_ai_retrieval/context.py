from __future__ import annotations

from typing import Any

from pydantic import Field

from clinical_ai_retrieval.schemas import (
    EvidenceDocument,
    EvidenceMetadata,
    EvidenceSourceType,
    RetrievalQuery,
    RetrievalModel,
)


class EvidenceCorpusItem(RetrievalModel):
    """Inline request corpus item; parsed into ``EvidenceDocument`` for retrieval."""

    source_id: str
    text: str = Field(min_length=1, max_length=100_000)
    source_type: EvidenceSourceType = EvidenceSourceType.SYNTHETIC_PROTOCOL
    title: str | None = None
    citation_id: str | None = None
    url: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    clinical_domains: list[str] = Field(default_factory=list)
    evidence_level: str | None = None
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RetrievalContext(RetrievalModel):
    query: RetrievalQuery
    inline_corpus: list[EvidenceDocument] = []

    @property
    def has_inline_corpus(self) -> bool:
        return bool(self.inline_corpus)


def build_retrieval_context(
    query: RetrievalQuery,
    payload: dict[str, Any],
) -> RetrievalContext:
    return RetrievalContext(
        query=query,
        inline_corpus=parse_inline_corpus(payload.get("evidence_corpus", [])),
    )


def parse_inline_corpus(items: list[Any]) -> list[EvidenceDocument]:
    documents: list[EvidenceDocument] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        documents.append(inline_corpus_item_to_document(item))
    return documents


def inline_corpus_item_to_document(item: dict[str, Any]) -> EvidenceDocument:
    source_type = EvidenceSourceType(item.get("source_type", EvidenceSourceType.SYNTHETIC_PROTOCOL))
    source_id = str(item["source_id"])
    citation_id = item.get("citation_id") or f"{source_type.value}:{source_id}"
    metadata = EvidenceMetadata(
        source_type=source_type,
        source_id=source_id,
        title=item.get("title"),
        url=item.get("url"),
        publication_year=item.get("publication_year"),
        clinical_domains=list(item.get("clinical_domains", [])),
        evidence_level=item.get("evidence_level"),
        citation_id=str(citation_id),
        extra={
            key: value
            for key, value in item.get("metadata", {}).items()
            if isinstance(value, str | int | float | bool)
        },
    )
    return EvidenceDocument(
        document_id=f"{source_type.value}:{source_id}",
        text=str(item["text"]),
        metadata=metadata,
    )
