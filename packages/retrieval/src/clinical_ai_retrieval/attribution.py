from clinical_ai_retrieval.schemas import Citation, RetrievalResult


class SourceAttributionTracker:
    """Track citations available from retrieval results for later answer verification."""

    def citations_from_results(self, results: list[RetrievalResult]) -> list[Citation]:
        citations: list[Citation] = []
        for result in results:
            citation_payload = result.payload.get("citation")
            if isinstance(citation_payload, dict):
                citations.append(Citation.model_validate(citation_payload))
            else:
                citations.append(
                    Citation(
                        citation_id=result.metadata.citation_id or result.chunk_id,
                        source_type=result.metadata.source_type,
                        source_id=result.metadata.source_id,
                        title=result.metadata.title,
                        url=result.metadata.url,
                        publication_year=result.metadata.publication_year,
                        section_path=result.metadata.section_path,
                        quote=result.text[:500],
                        attribution_text=result.metadata.citation_text
                        or self._fallback_attribution(result),
                    )
                )
        return citations

    def verify_claimed_citations(
        self,
        *,
        claimed_citation_ids: list[str],
        available_citations: list[Citation],
    ) -> dict[str, bool]:
        available_ids = {citation.citation_id for citation in available_citations}
        return {
            citation_id: citation_id in available_ids
            for citation_id in claimed_citation_ids
        }

    def _fallback_attribution(self, result: RetrievalResult) -> str:
        title = result.metadata.title or result.metadata.source_id
        year = f" ({result.metadata.publication_year})" if result.metadata.publication_year else ""
        source = result.metadata.source_type.value.replace("_", " ")
        return f"{title}{year}. {source}: {result.metadata.source_id}."
