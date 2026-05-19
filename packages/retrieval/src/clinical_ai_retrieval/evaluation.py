from clinical_ai_retrieval.schemas import EvidencePackage, RetrievalModel


class RetrievalEvaluationCase(RetrievalModel):
    query: str
    expected_source_ids: list[str] = []
    expected_citation_ids: list[str] = []
    minimum_confidence: float = 0.0


class RetrievalEvaluationResult(RetrievalModel):
    query: str
    hit_rate: float
    citation_hit_rate: float
    confidence_score: float
    passed: bool


class RetrievalEvaluator:
    def evaluate(
        self,
        *,
        case: RetrievalEvaluationCase,
        package: EvidencePackage,
    ) -> RetrievalEvaluationResult:
        retrieved_source_ids = {item.metadata.source_id for item in package.evidence}
        retrieved_citation_ids = {citation.citation_id for citation in package.citations}
        hit_rate = fraction_present(case.expected_source_ids, retrieved_source_ids)
        citation_hit_rate = fraction_present(case.expected_citation_ids, retrieved_citation_ids)
        passed = (
            hit_rate >= 1.0
            and citation_hit_rate >= 1.0
            and package.confidence_score >= case.minimum_confidence
        )
        return RetrievalEvaluationResult(
            query=case.query,
            hit_rate=hit_rate,
            citation_hit_rate=citation_hit_rate,
            confidence_score=package.confidence_score,
            passed=passed,
        )


def fraction_present(expected: list[str], observed: set[str]) -> float:
    if not expected:
        return 1.0
    return sum(1 for item in expected if item in observed) / len(expected)
