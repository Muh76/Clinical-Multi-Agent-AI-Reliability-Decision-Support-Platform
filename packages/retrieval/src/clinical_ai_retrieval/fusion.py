from clinical_ai_retrieval.schemas import FusionStrategy, RetrievalResult
from clinical_ai_retrieval.scoring import attach_reliability_scores


def fuse_results(
    *,
    dense_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    dense_weight: float,
    bm25_weight: float,
    strategy: FusionStrategy,
    limit: int,
) -> list[RetrievalResult]:
    if strategy == FusionStrategy.RECIPROCAL_RANK_FUSION:
        return reciprocal_rank_fusion(dense_results, bm25_results, limit=limit)
    return weighted_sum_fusion(
        dense_results=dense_results,
        bm25_results=bm25_results,
        dense_weight=dense_weight,
        bm25_weight=bm25_weight,
        limit=limit,
    )


def weighted_sum_fusion(
    *,
    dense_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    dense_weight: float,
    bm25_weight: float,
    limit: int,
) -> list[RetrievalResult]:
    merged: dict[str, RetrievalResult] = {}
    for result in dense_results:
        merged[result.chunk_id] = result.model_copy(
            update={
                "dense_score": result.score,
                "score": dense_weight * result.score,
            }
        )
    for result in bm25_results:
        existing = merged.get(result.chunk_id)
        if existing is None:
            merged[result.chunk_id] = result.model_copy(
                update={
                    "lexical_score": result.score,
                    "score": bm25_weight * result.score,
                }
            )
            continue
        merged[result.chunk_id] = existing.model_copy(
            update={
                "lexical_score": result.score,
                "score": existing.score + bm25_weight * result.score,
            }
        )
    ranked = sorted(merged.values(), key=lambda result: result.score, reverse=True)
    return attach_reliability_scores(ranked[:limit])


def reciprocal_rank_fusion(
    dense_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    *,
    limit: int,
    rank_constant: int = 60,
) -> list[RetrievalResult]:
    merged: dict[str, RetrievalResult] = {}
    scores: dict[str, float] = {}
    for result_list in (dense_results, bm25_results):
        for rank, result in enumerate(result_list, start=1):
            merged.setdefault(result.chunk_id, result)
            scores[result.chunk_id] = (
                scores.get(result.chunk_id, 0.0) + 1.0 / (rank_constant + rank)
            )
    ranked = sorted(
        (
            result.model_copy(update={"score": scores[result.chunk_id]})
            for result in merged.values()
        ),
        key=lambda result: result.score,
        reverse=True,
    )
    return attach_reliability_scores(ranked[:limit])
