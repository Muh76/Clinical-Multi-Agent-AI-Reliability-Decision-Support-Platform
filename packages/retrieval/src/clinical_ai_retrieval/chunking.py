from collections.abc import Iterable

from clinical_ai_retrieval.schemas import Citation, EvidenceChunk, EvidenceDocument


class TextChunker:
    def __init__(self, *, max_chars: int = 1_800, overlap_chars: int = 250) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if overlap_chars < 0:
            raise ValueError("overlap_chars cannot be negative")
        if overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, document: EvidenceDocument) -> list[EvidenceChunk]:
        segments = list(self._split_text(document.text))
        return [
            EvidenceChunk(
                chunk_id=f"{document.document_id}:{index}",
                document_id=document.document_id,
                text=segment,
                chunk_index=index,
                metadata=document.metadata,
                citation=chunk_citation(document, index, segment),
                token_estimate=max(1, len(segment) // 4),
            )
            for index, segment in enumerate(segments)
        ]

    def _split_text(self, text: str) -> Iterable[str]:
        clean_text = " ".join(text.split())
        if not clean_text:
            return
        start = 0
        while start < len(clean_text):
            end = min(start + self.max_chars, len(clean_text))
            if end < len(clean_text):
                boundary = clean_text.rfind(". ", start, end)
                if boundary > start + self.max_chars // 2:
                    end = boundary + 1
            yield clean_text[start:end].strip()
            if end == len(clean_text):
                break
            start = max(0, end - self.overlap_chars)


def chunk_citation(document: EvidenceDocument, chunk_index: int, text: str) -> Citation:
    metadata = document.metadata
    citation_id = metadata.citation_id or f"{document.document_id}:{chunk_index}"
    title = metadata.title or metadata.source_id
    year = f" ({metadata.publication_year})" if metadata.publication_year else ""
    section = f", {' > '.join(metadata.section_path)}" if metadata.section_path else ""
    source_label = metadata.source_type.value.replace("_", " ")
    attribution = f"{title}{year}. {source_label}: {metadata.source_id}{section}."
    return Citation(
        citation_id=citation_id,
        source_type=metadata.source_type,
        source_id=metadata.source_id,
        title=metadata.title,
        url=metadata.url,
        publication_year=metadata.publication_year,
        section_path=metadata.section_path,
        quote=text[:500],
        attribution_text=metadata.citation_text or attribution,
    )
