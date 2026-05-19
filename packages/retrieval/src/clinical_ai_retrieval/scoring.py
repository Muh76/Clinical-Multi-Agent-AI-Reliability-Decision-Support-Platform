from clinical_ai_retrieval.schemas import EvidenceSourceType, RetrievalResult


SOURCE_RELIABILITY_PRIORS: dict[EvidenceSourceType, float] = {
    EvidenceSourceType.NICE_GUIDELINE: 0.95,
    EvidenceSourceType.LOCAL_POLICY: 0.88,
    EvidenceSourceType.PUBMED: 0.78,
    EvidenceSourceType.SYNTHETIC_PROTOCOL: 0.55,
    EvidenceSourceType.IMAGING_REPORT_METADATA: 0.45,
}


EVIDENCE_LEVEL_BOOSTS: dict[str, float] = {
    "guideline": 0.08,
    "systematic_review": 0.06,
    "randomized_trial": 0.04,
    "primary_study": 0.02,
    "expert_consensus": 0.01,
}


def source_reliability_score(result: RetrievalResult) -> float:
    base_score = SOURCE_RELIABILITY_PRIORS.get(result.metadata.source_type, 0.5)
    if result.metadata.evidence_level:
        base_score += EVIDENCE_LEVEL_BOOSTS.get(result.metadata.evidence_level.lower(), 0.0)
    if result.metadata.publication_year is not None and result.metadata.publication_year < 2010:
        base_score -= 0.08
    return clamp(base_score)


def confidence_score(result: RetrievalResult) -> float:
    semantic_score = normalize_similarity(result.score)
    lexical_score = result.lexical_score if result.lexical_score is not None else semantic_score
    rerank_score = normalize_rerank(result.rerank_score)
    reliability = result.source_reliability_score
    if result.rerank_score is not None:
        return clamp(
            (0.35 * semantic_score)
            + (0.35 * rerank_score)
            + (0.2 * reliability)
            + (0.1 * lexical_score)
        )
    return clamp((0.55 * semantic_score) + (0.25 * lexical_score) + (0.2 * reliability))


def attach_reliability_scores(results: list[RetrievalResult]) -> list[RetrievalResult]:
    scored_results: list[RetrievalResult] = []
    for result in results:
        reliability = source_reliability_score(result)
        interim = result.model_copy(update={"source_reliability_score": reliability})
        scored_results.append(
            interim.model_copy(update={"confidence_score": confidence_score(interim)})
        )
    return scored_results


def normalize_similarity(value: float) -> float:
    return clamp(value if value <= 1.0 else value / (1.0 + value))


def normalize_rerank(value: float | None) -> float:
    if value is None:
        return 0.0
    return clamp(1.0 / (1.0 + pow(2.718281828, -value)))


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
