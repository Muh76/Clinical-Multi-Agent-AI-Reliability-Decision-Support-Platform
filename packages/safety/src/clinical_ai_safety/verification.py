from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from clinical_ai_safety.hallucination import (
    ClaimToValidate,
    EscalationRecommendation,
    EvidenceReference,
    clamp01,
    clinical_tokens,
    lexical_support_score,
)


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNTRACEABLE = "untraceable"
    UNKNOWN = "unknown"


class CitationTraceStatus(StrEnum):
    TRACEABLE = "traceable"
    PARTIAL = "partial"
    MISSING = "missing"
    INVALID = "invalid"


class VerificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CitationVerificationResult(VerificationModel):
    claim_id: str
    citation_ids: list[str] = Field(default_factory=list)
    valid_citation_ids: list[str] = Field(default_factory=list)
    invalid_citation_ids: list[str] = Field(default_factory=list)
    status: CitationTraceStatus
    traceability_score: float = Field(ge=0.0, le=1.0)
    explanation: str


class ClaimEvidenceMatch(VerificationModel):
    claim_id: str
    claim_text: str
    status: VerificationStatus
    support_score: float = Field(ge=0.0, le=1.0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[str] = Field(default_factory=list)
    source_trust_score: float = Field(ge=0.0, le=1.0)
    explanation: str


class SourceTrustScore(VerificationModel):
    evidence_id: str
    citation_id: str
    source_id: str
    source_type: str
    trust_score: float = Field(ge=0.0, le=1.0)
    reliability_score: float = Field(ge=0.0, le=1.0)
    source_type_score: float = Field(ge=0.0, le=1.0)
    evidence_level_score: float = Field(ge=0.0, le=1.0)
    recency_score: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class EvidenceCoverageSummary(VerificationModel):
    claim_count: int = Field(ge=0)
    verified_count: int = Field(ge=0)
    partially_verified_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    contradicted_count: int = Field(ge=0)
    untraceable_count: int = Field(ge=0)
    evidence_coverage_score: float = Field(ge=0.0, le=1.0)
    citation_traceability_score: float = Field(ge=0.0, le=1.0)


class EvidenceVerificationRequest(VerificationModel):
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    claims: list[ClaimToValidate] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    available_citation_ids: list[str] = Field(default_factory=list)
    upstream_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceVerificationReport(VerificationModel):
    report_id: str
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    overall_status: VerificationStatus
    verification_confidence: float = Field(ge=0.0, le=1.0)
    evidence_coverage: EvidenceCoverageSummary
    source_trust_score: float = Field(ge=0.0, le=1.0)
    contradiction_count: int = Field(ge=0)
    claim_matches: list[ClaimEvidenceMatch] = Field(default_factory=list)
    citation_results: list[CitationVerificationResult] = Field(default_factory=list)
    source_trust: list[SourceTrustScore] = Field(default_factory=list)
    unsupported_claim_ids: list[str] = Field(default_factory=list)
    contradicted_claim_ids: list[str] = Field(default_factory=list)
    escalation_recommendation: EscalationRecommendation
    failed_checks: list[str] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceVerificationLayer:
    async def verify(
        self,
        request: EvidenceVerificationRequest,
    ) -> EvidenceVerificationReport:
        return verify_evidence_support(request)


def verify_evidence_support(
    request: EvidenceVerificationRequest,
) -> EvidenceVerificationReport:
    citation_allow_list = set(request.available_citation_ids) or {
        evidence.citation_id for evidence in request.evidence
    }
    evidence_by_citation = {evidence.citation_id: evidence for evidence in request.evidence}
    source_trust = [score_source_trust(evidence) for evidence in request.evidence]
    trust_by_evidence_id = {score.evidence_id: score.trust_score for score in source_trust}

    citation_results = [
        verify_citations(claim, citation_allow_list) for claim in request.claims
    ]
    claim_matches = [
        match_claim_to_evidence(
            claim=claim,
            evidence_by_citation=evidence_by_citation,
            citation_allow_list=citation_allow_list,
            all_evidence=request.evidence,
            trust_by_evidence_id=trust_by_evidence_id,
        )
        for claim in request.claims
    ]
    coverage = summarize_coverage(claim_matches, citation_results)
    source_trust_score = aggregate_source_trust(source_trust)
    contradiction_count = sum(
        1 for match in claim_matches if match.status == VerificationStatus.CONTRADICTED
    )
    verification_confidence = calculate_verification_confidence(
        coverage=coverage,
        source_trust_score=source_trust_score,
        contradiction_count=contradiction_count,
        claim_count=len(request.claims),
        upstream_confidence=request.upstream_confidence,
    )
    overall_status = determine_overall_status(claim_matches, coverage)
    failed_checks = verification_failed_checks(
        request=request,
        coverage=coverage,
        claim_matches=claim_matches,
        source_trust_score=source_trust_score,
    )
    unsupported_claim_ids = [
        match.claim_id
        for match in claim_matches
        if match.status in {VerificationStatus.UNSUPPORTED, VerificationStatus.UNTRACEABLE}
    ]
    contradicted_claim_ids = [
        match.claim_id
        for match in claim_matches
        if match.status == VerificationStatus.CONTRADICTED
    ]
    escalation = verification_escalation(
        overall_status=overall_status,
        verification_confidence=verification_confidence,
        contradicted_claim_ids=contradicted_claim_ids,
        unsupported_claim_ids=unsupported_claim_ids,
    )
    return EvidenceVerificationReport(
        report_id=f"evidence-verification-report-{uuid4()}",
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        overall_status=overall_status,
        verification_confidence=verification_confidence,
        evidence_coverage=coverage,
        source_trust_score=source_trust_score,
        contradiction_count=contradiction_count,
        claim_matches=claim_matches,
        citation_results=citation_results,
        source_trust=source_trust,
        unsupported_claim_ids=unsupported_claim_ids,
        contradicted_claim_ids=contradicted_claim_ids,
        escalation_recommendation=escalation,
        failed_checks=failed_checks,
        observability=verification_observability_payload(
            request=request,
            overall_status=overall_status,
            verification_confidence=verification_confidence,
            coverage=coverage,
            source_trust_score=source_trust_score,
            contradiction_count=contradiction_count,
            escalation=escalation,
            failed_checks=failed_checks,
        ),
    )


def verify_citations(
    claim: ClaimToValidate,
    citation_allow_list: set[str],
) -> CitationVerificationResult:
    if not claim.citation_ids:
        return CitationVerificationResult(
            claim_id=claim.claim_id,
            status=CitationTraceStatus.MISSING,
            traceability_score=0.0,
            explanation="Claim has no citation IDs to trace.",
        )

    valid = [
        citation_id for citation_id in claim.citation_ids if citation_id in citation_allow_list
    ]
    invalid = [
        citation_id for citation_id in claim.citation_ids if citation_id not in citation_allow_list
    ]
    if invalid and valid:
        status = CitationTraceStatus.PARTIAL
    elif invalid:
        status = CitationTraceStatus.INVALID
    else:
        status = CitationTraceStatus.TRACEABLE
    return CitationVerificationResult(
        claim_id=claim.claim_id,
        citation_ids=claim.citation_ids,
        valid_citation_ids=valid,
        invalid_citation_ids=invalid,
        status=status,
        traceability_score=len(valid) / len(claim.citation_ids),
        explanation=citation_explanation(status, valid, invalid),
    )


def match_claim_to_evidence(
    *,
    claim: ClaimToValidate,
    evidence_by_citation: dict[str, EvidenceReference],
    citation_allow_list: set[str],
    all_evidence: list[EvidenceReference],
    trust_by_evidence_id: dict[str, float],
) -> ClaimEvidenceMatch:
    if not claim.citation_ids:
        return claim_match(
            claim=claim,
            status=VerificationStatus.UNTRACEABLE,
            explanation="Claim cannot be verified because it has no citation IDs.",
        )

    if any(citation_id not in citation_allow_list for citation_id in claim.citation_ids):
        return claim_match(
            claim=claim,
            status=VerificationStatus.UNTRACEABLE,
            explanation="Claim includes citation IDs outside the retrieved citation allow-list.",
        )

    cited_evidence = [
        evidence_by_citation[citation_id]
        for citation_id in claim.citation_ids
        if citation_id in evidence_by_citation
    ]
    if not cited_evidence:
        return claim_match(
            claim=claim,
            status=VerificationStatus.UNSUPPORTED,
            explanation="Claim citations are traceable but no evidence payload was provided.",
        )

    support_scores = [
        lexical_support_score(claim.text, evidence.text) for evidence in cited_evidence
    ]
    support_score = max(support_scores)
    cited_evidence_ids = [evidence.evidence_id for evidence in cited_evidence]
    source_trust_score = aggregate_values(
        [trust_by_evidence_id.get(evidence_id, 0.5) for evidence_id in cited_evidence_ids]
    )
    contradictory_ids = contradiction_evidence_ids(claim.text, all_evidence)
    status = verification_status(support_score, contradictory_ids)
    coverage_score = coverage_score_for_status(status, support_score)
    return ClaimEvidenceMatch(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        status=status,
        support_score=support_score,
        coverage_score=coverage_score,
        cited_evidence_ids=cited_evidence_ids,
        citation_ids=claim.citation_ids,
        contradictory_evidence_ids=contradictory_ids,
        source_trust_score=source_trust_score,
        explanation=match_explanation(status, support_score, contradictory_ids),
    )


def claim_match(
    *,
    claim: ClaimToValidate,
    status: VerificationStatus,
    explanation: str,
) -> ClaimEvidenceMatch:
    return ClaimEvidenceMatch(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        status=status,
        support_score=0.0,
        coverage_score=0.0,
        source_trust_score=0.0,
        explanation=explanation,
    )


def score_source_trust(evidence: EvidenceReference) -> SourceTrustScore:
    source_type_score, source_note = score_source_type(evidence.source_type)
    evidence_level_score, level_note = score_evidence_level(evidence.metadata.get("evidence_level"))
    recency_score, recency_note = score_recency(evidence.metadata.get("publication_year"))
    trust_score = clamp01(
        0.35 * evidence.reliability_score
        + 0.30 * source_type_score
        + 0.20 * evidence_level_score
        + 0.15 * recency_score
    )
    notes = [note for note in (source_note, level_note, recency_note) if note]
    return SourceTrustScore(
        evidence_id=evidence.evidence_id,
        citation_id=evidence.citation_id,
        source_id=evidence.source_id,
        source_type=evidence.source_type,
        trust_score=trust_score,
        reliability_score=evidence.reliability_score,
        source_type_score=source_type_score,
        evidence_level_score=evidence_level_score,
        recency_score=recency_score,
        notes=notes,
    )


def score_source_type(source_type: str) -> tuple[float, str]:
    normalized = source_type.lower()
    scores = {
        "nice_guideline": 0.95,
        "local_policy": 0.85,
        "pubmed": 0.80,
        "synthetic_protocol": 0.45,
        "imaging_report_metadata": 0.55,
    }
    score = scores.get(normalized, 0.50)
    if normalized == "synthetic_protocol":
        return score, "Synthetic protocol evidence is not treated as clinical authority."
    if normalized not in scores:
        return score, "Unknown source type uses neutral trust score."
    return score, ""


def score_evidence_level(value: Any) -> tuple[float, str]:
    if value is None:
        return 0.50, "Evidence level missing."
    normalized = str(value).lower().replace(" ", "_")
    scores = {
        "guideline": 0.95,
        "systematic_review": 0.90,
        "randomized_controlled_trial": 0.82,
        "primary_study": 0.72,
        "cohort": 0.68,
        "case_control": 0.60,
        "expert_consensus": 0.55,
        "local_policy": 0.75,
    }
    return scores.get(normalized, 0.55), ""


def score_recency(value: Any) -> tuple[float, str]:
    if value is None:
        return 0.50, "Publication year missing."
    try:
        year = int(value)
    except (TypeError, ValueError):
        return 0.50, "Publication year could not be parsed."
    current_year = datetime.now(UTC).year
    age = max(0, current_year - year)
    if age <= 5:
        return 1.0, ""
    if age <= 10:
        return 0.80, ""
    if age <= 20:
        return 0.60, "Evidence is older than 10 years."
    return 0.40, "Evidence is older than 20 years."


def contradiction_evidence_ids(
    claim_text: str,
    evidence: list[EvidenceReference],
) -> list[str]:
    claim_tokens = clinical_tokens(claim_text)
    if not is_assertive_or_recommendation(claim_text):
        return []
    contradiction_markers = (
        "contraindicated",
        "avoid",
        "not recommended",
        "insufficient evidence",
        "no evidence",
        "does not support",
        "harm",
    )
    matches: list[str] = []
    for item in evidence:
        evidence_text = item.text.lower()
        if not any(marker in evidence_text for marker in contradiction_markers):
            continue
        if claim_tokens & clinical_tokens(item.text):
            matches.append(item.evidence_id)
    return matches


def is_assertive_or_recommendation(text: str) -> bool:
    lowered = text.lower()
    markers = ("recommend", "should", "must", "supports", "indicates", "safe", "high risk")
    return any(marker in lowered for marker in markers)


def verification_status(
    support_score: float,
    contradictory_ids: list[str],
) -> VerificationStatus:
    if contradictory_ids:
        return VerificationStatus.CONTRADICTED
    if support_score >= 0.72:
        return VerificationStatus.VERIFIED
    if support_score >= 0.38:
        return VerificationStatus.PARTIALLY_VERIFIED
    return VerificationStatus.UNSUPPORTED


def coverage_score_for_status(status: VerificationStatus, support_score: float) -> float:
    if status == VerificationStatus.VERIFIED:
        return clamp01(0.85 + 0.15 * support_score)
    if status == VerificationStatus.PARTIALLY_VERIFIED:
        return clamp01(0.45 + 0.35 * support_score)
    return 0.0


def summarize_coverage(
    claim_matches: list[ClaimEvidenceMatch],
    citation_results: list[CitationVerificationResult],
) -> EvidenceCoverageSummary:
    claim_count = len(claim_matches)
    if claim_count == 0:
        return EvidenceCoverageSummary(
            claim_count=0,
            verified_count=0,
            partially_verified_count=0,
            unsupported_count=0,
            contradicted_count=0,
            untraceable_count=0,
            evidence_coverage_score=0.0,
            citation_traceability_score=1.0,
        )

    evidence_coverage_score = aggregate_values(
        [match.coverage_score for match in claim_matches]
    )
    citation_traceability_score = aggregate_values(
        [result.traceability_score for result in citation_results]
    )
    return EvidenceCoverageSummary(
        claim_count=claim_count,
        verified_count=count_status(claim_matches, VerificationStatus.VERIFIED),
        partially_verified_count=count_status(
            claim_matches,
            VerificationStatus.PARTIALLY_VERIFIED,
        ),
        unsupported_count=count_status(claim_matches, VerificationStatus.UNSUPPORTED),
        contradicted_count=count_status(claim_matches, VerificationStatus.CONTRADICTED),
        untraceable_count=count_status(claim_matches, VerificationStatus.UNTRACEABLE),
        evidence_coverage_score=evidence_coverage_score,
        citation_traceability_score=citation_traceability_score,
    )


def calculate_verification_confidence(
    *,
    coverage: EvidenceCoverageSummary,
    source_trust_score: float,
    contradiction_count: int,
    claim_count: int,
    upstream_confidence: float | None,
) -> float:
    contradiction_penalty = contradiction_count / claim_count if claim_count else 0.0
    confidence = (
        0.45 * coverage.evidence_coverage_score
        + 0.25 * coverage.citation_traceability_score
        + 0.20 * source_trust_score
        + 0.10 * (1.0 - contradiction_penalty)
    )
    if (
        upstream_confidence is not None
        and upstream_confidence >= 0.80
        and coverage.evidence_coverage_score < 0.60
    ):
        confidence -= 0.15
    return clamp01(confidence)


def determine_overall_status(
    claim_matches: list[ClaimEvidenceMatch],
    coverage: EvidenceCoverageSummary,
) -> VerificationStatus:
    if not claim_matches:
        return VerificationStatus.UNKNOWN
    if coverage.contradicted_count:
        return VerificationStatus.CONTRADICTED
    if coverage.untraceable_count:
        return VerificationStatus.UNTRACEABLE
    if coverage.unsupported_count:
        return VerificationStatus.UNSUPPORTED
    if coverage.partially_verified_count:
        return VerificationStatus.PARTIALLY_VERIFIED
    return VerificationStatus.VERIFIED


def verification_failed_checks(
    *,
    request: EvidenceVerificationRequest,
    coverage: EvidenceCoverageSummary,
    claim_matches: list[ClaimEvidenceMatch],
    source_trust_score: float,
) -> list[str]:
    checks: list[str] = []
    if not request.evidence:
        checks.append("evidence.empty")
    if coverage.citation_traceability_score < 1.0:
        checks.append("citation.traceability_incomplete")
    if coverage.evidence_coverage_score < 0.70:
        checks.append("evidence.coverage_low")
    if source_trust_score < 0.60:
        checks.append("source.trust_low")
    if any(match.status == VerificationStatus.CONTRADICTED for match in claim_matches):
        checks.append("evidence.contradiction")
    if (
        request.upstream_confidence is not None
        and request.upstream_confidence >= 0.80
        and coverage.evidence_coverage_score < 0.60
    ):
        checks.append("confidence.overstated")
    return checks


def verification_escalation(
    *,
    overall_status: VerificationStatus,
    verification_confidence: float,
    contradicted_claim_ids: list[str],
    unsupported_claim_ids: list[str],
) -> EscalationRecommendation:
    if contradicted_claim_ids:
        return EscalationRecommendation.BLOCK
    if overall_status in {VerificationStatus.UNSUPPORTED, VerificationStatus.UNTRACEABLE}:
        return EscalationRecommendation.HUMAN_REVIEW
    if unsupported_claim_ids or verification_confidence < 0.65:
        return EscalationRecommendation.QUALIFY
    return EscalationRecommendation.ALLOW


def verification_observability_payload(
    *,
    request: EvidenceVerificationRequest,
    overall_status: VerificationStatus,
    verification_confidence: float,
    coverage: EvidenceCoverageSummary,
    source_trust_score: float,
    contradiction_count: int,
    escalation: EscalationRecommendation,
    failed_checks: list[str],
) -> dict[str, Any]:
    return {
        "case_id": request.case_id,
        "workflow_id": request.workflow_id,
        "trace_id": request.trace_id,
        "claim_count": len(request.claims),
        "evidence_count": len(request.evidence),
        "overall_status": overall_status.value,
        "verification_confidence": verification_confidence,
        "evidence_coverage_score": coverage.evidence_coverage_score,
        "citation_traceability_score": coverage.citation_traceability_score,
        "source_trust_score": source_trust_score,
        "contradiction_count": contradiction_count,
        "escalation_recommendation": escalation.value,
        "failed_checks": failed_checks,
    }


def citation_explanation(
    status: CitationTraceStatus,
    valid: list[str],
    invalid: list[str],
) -> str:
    if status == CitationTraceStatus.MISSING:
        return "Claim has no citations."
    if status == CitationTraceStatus.INVALID:
        return f"Claim citations are not traceable: {', '.join(invalid)}."
    if status == CitationTraceStatus.PARTIAL:
        return (
            f"Claim has traceable citations {', '.join(valid)} and invalid citations "
            f"{', '.join(invalid)}."
        )
    return "All claim citations are traceable to retrieved evidence."


def match_explanation(
    status: VerificationStatus,
    support_score: float,
    contradictory_ids: list[str],
) -> str:
    if status == VerificationStatus.CONTRADICTED:
        return f"Claim is contradicted by retrieved evidence: {', '.join(contradictory_ids)}."
    if status == VerificationStatus.VERIFIED:
        return f"Claim is verified by cited evidence with support score {support_score:.2f}."
    if status == VerificationStatus.PARTIALLY_VERIFIED:
        return f"Claim is partially verified with support score {support_score:.2f}."
    return f"Claim is not supported by cited evidence; support score {support_score:.2f}."


def aggregate_source_trust(scores: list[SourceTrustScore]) -> float:
    return aggregate_values([score.trust_score for score in scores])


def aggregate_values(values: list[float]) -> float:
    if not values:
        return 0.0
    return clamp01(sum(values) / len(values))


def count_status(
    matches: list[ClaimEvidenceMatch],
    status: VerificationStatus,
) -> int:
    return sum(1 for match in matches if match.status == status)
