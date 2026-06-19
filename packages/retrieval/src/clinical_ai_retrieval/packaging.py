from clinical_ai_retrieval.attribution import SourceAttributionTracker
from clinical_ai_retrieval.schemas import (
    EvidencePackage,
    RetrievalBackend,
    RetrievalDiagnostics,
    RetrievalEvidenceItem,
    RetrievalQuery,
    RetrievalResult,
)


def package_evidence(
    *,
    query: RetrievalQuery,
    results: list[RetrievalResult],
    backend: RetrievalBackend,
    dense_count: int,
    bm25_count: int,
    reranked: bool,
    attribution_tracker: SourceAttributionTracker | None = None,
) -> EvidencePackage:
    tracker = attribution_tracker or SourceAttributionTracker()
    citations = tracker.citations_from_results(results)
    evidence = [
        RetrievalEvidenceItem(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            text=result.text,
            citation=citation,
            metadata=result.metadata,
            score=result.score,
            confidence_score=result.confidence_score,
            source_reliability_score=result.source_reliability_score,
            rank=rank,
            scoring_components=scoring_components(result),
        )
        for rank, (result, citation) in enumerate(zip(results, citations, strict=True), start=1)
    ]
    diagnostics = RetrievalDiagnostics(
        mode=query.mode,
        fusion_strategy=query.fusion_strategy,
        backend=backend,
        dense_result_count=dense_count,
        bm25_result_count=bm25_count,
        reranked=reranked,
        filters_applied=query.filters != type(query.filters)(),
        reliability_notes=reliability_notes(results),
    )
    package_confidence = (
        sum(item.confidence_score for item in evidence) / len(evidence) if evidence else 0.0
    )
    return EvidencePackage(
        query=query.query,
        evidence=evidence,
        citations=citations,
        diagnostics=diagnostics,
        confidence_score=package_confidence,
    )


def scoring_components(result: RetrievalResult) -> dict[str, float]:
    components = {
        "final": result.score,
        "confidence": result.confidence_score,
        "source_reliability": result.source_reliability_score,
    }
    if result.dense_score is not None:
        components["dense"] = result.dense_score
    if result.lexical_score is not None:
        components["bm25"] = result.lexical_score
    if result.rerank_score is not None:
        components["rerank"] = result.rerank_score
    return components


def reliability_notes(results: list[RetrievalResult]) -> list[str]:
    notes: list[str] = []
    if not results:
        return ["No evidence chunks were retrieved for this query."]
    if all(result.metadata.source_type.value == "synthetic_protocol" for result in results):
        notes.append(
            "Only synthetic protocol evidence was retrieved; avoid treating it as clinical authority."
        )
    if any(result.confidence_score < 0.35 for result in results):
        notes.append("Some retrieved chunks have low confidence and should be reviewed before use.")
    if len({result.metadata.source_type for result in results}) > 1:
        notes.append(
            "Evidence package includes multiple source types; downstream answers should cite source class."
        )
    return notes
