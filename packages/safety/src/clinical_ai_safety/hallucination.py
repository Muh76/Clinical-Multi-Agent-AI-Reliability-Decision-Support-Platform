from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from clinical_ai_shared.types import RiskSeverity
from pydantic import BaseModel, ConfigDict, Field


class HallucinationRiskBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ClaimSupportStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    MISSING_CITATION = "missing_citation"
    INVALID_CITATION = "invalid_citation"


class EscalationRecommendation(StrEnum):
    ALLOW = "allow"
    QUALIFY = "qualify"
    HUMAN_REVIEW = "human_review"
    BLOCK = "block"


class HallucinationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceReference(HallucinationModel):
    evidence_id: str
    citation_id: str
    text: str
    source_id: str
    source_type: str
    title: str | None = None
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimToValidate(HallucinationModel):
    claim_id: str
    text: str
    citation_ids: list[str] = Field(default_factory=list)
    claim_type: str = "clinical_claim"
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimGroundingResult(HallucinationModel):
    claim_id: str
    claim_text: str
    status: ClaimSupportStatus
    support_score: float = Field(ge=0.0, le=1.0)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    missing_citation: bool = False
    invalid_citations: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str


class HallucinationDetectionRequest(HallucinationModel):
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    claims: list[ClaimToValidate] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    available_citation_ids: list[str] = Field(default_factory=list)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HallucinationReport(HallucinationModel):
    report_id: str
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    hallucination_risk_score: float = Field(ge=0.0, le=1.0)
    risk_band: HallucinationRiskBand
    grounding_confidence: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[ClaimGroundingResult] = Field(default_factory=list)
    claim_results: list[ClaimGroundingResult] = Field(default_factory=list)
    escalation_recommendation: EscalationRecommendation
    failed_checks: list[str] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HallucinationDetectionEngine:
    async def evaluate(self, request: HallucinationDetectionRequest) -> HallucinationReport:
        return evaluate_hallucination_risk(request)


def evaluate_hallucination_risk(
    request: HallucinationDetectionRequest,
) -> HallucinationReport:
    citation_allow_list = set(request.available_citation_ids) or {
        evidence.citation_id for evidence in request.evidence
    }
    evidence_by_citation = {evidence.citation_id: evidence for evidence in request.evidence}
    claim_results = [
        evaluate_claim(
            claim=claim,
            evidence_by_citation=evidence_by_citation,
            citation_allow_list=citation_allow_list,
            all_evidence=request.evidence,
        )
        for claim in request.claims
    ]
    citation_coverage = calculate_citation_coverage(request.claims, citation_allow_list)
    grounding_confidence = calculate_grounding_confidence(claim_results, request.evidence)
    hallucination_risk_score = calculate_hallucination_risk(
        claim_results=claim_results,
        citation_coverage=citation_coverage,
        grounding_confidence=grounding_confidence,
        upstream_confidence=request.confidence_score,
    )
    failed_checks = failed_validation_checks(claim_results, citation_coverage, request.evidence)
    unsupported_claims = [
        result
        for result in claim_results
        if result.status
        in {
            ClaimSupportStatus.UNSUPPORTED,
            ClaimSupportStatus.CONTRADICTED,
            ClaimSupportStatus.MISSING_CITATION,
            ClaimSupportStatus.INVALID_CITATION,
        }
    ]
    risk_band = risk_band_from_score(hallucination_risk_score)
    escalation = escalation_recommendation(risk_band, unsupported_claims)
    return HallucinationReport(
        report_id=f"hallucination-report-{uuid4()}",
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        hallucination_risk_score=hallucination_risk_score,
        risk_band=risk_band,
        grounding_confidence=grounding_confidence,
        citation_coverage=citation_coverage,
        unsupported_claims=unsupported_claims,
        claim_results=claim_results,
        escalation_recommendation=escalation,
        failed_checks=failed_checks,
        observability=observability_payload(
            request,
            hallucination_risk_score,
            risk_band,
            grounding_confidence,
            citation_coverage,
            escalation,
            failed_checks,
        ),
    )


def evaluate_claim(
    *,
    claim: ClaimToValidate,
    evidence_by_citation: dict[str, EvidenceReference],
    citation_allow_list: set[str],
    all_evidence: list[EvidenceReference],
) -> ClaimGroundingResult:
    if not claim.citation_ids:
        return ClaimGroundingResult(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            status=ClaimSupportStatus.MISSING_CITATION,
            support_score=0.0,
            missing_citation=True,
            explanation=(
                "Claim has no citation IDs and cannot be verified against "
                "retrieved evidence."
            ),
        )

    invalid_citations = [
        citation_id for citation_id in claim.citation_ids if citation_id not in citation_allow_list
    ]
    if invalid_citations:
        return ClaimGroundingResult(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            status=ClaimSupportStatus.INVALID_CITATION,
            support_score=0.0,
            invalid_citations=invalid_citations,
            explanation="Claim cites evidence IDs that were not available in retrieved evidence.",
        )

    cited_evidence = [
        evidence_by_citation[citation_id]
        for citation_id in claim.citation_ids
        if citation_id in evidence_by_citation
    ]
    if not cited_evidence:
        return ClaimGroundingResult(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            status=ClaimSupportStatus.UNSUPPORTED,
            support_score=0.0,
            explanation=(
                "Claim citations are allowed but no matching evidence payload "
                "was supplied."
            ),
        )

    support_score = max(
        lexical_support_score(claim.text, evidence.text)
        for evidence in cited_evidence
    )
    contradictory_ids = contradictory_evidence_ids(claim.text, all_evidence)
    status = support_status(support_score, contradictory_ids)
    return ClaimGroundingResult(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        status=status,
        support_score=support_score,
        cited_evidence_ids=[evidence.evidence_id for evidence in cited_evidence],
        contradictory_evidence_ids=contradictory_ids,
        explanation=claim_explanation(status, support_score, contradictory_ids),
    )


def lexical_support_score(claim_text: str, evidence_text: str) -> float:
    claim_tokens = clinical_tokens(claim_text)
    evidence_tokens = clinical_tokens(evidence_text)
    if not claim_tokens:
        return 0.0
    overlap = len(claim_tokens & evidence_tokens)
    coverage = overlap / len(claim_tokens)
    density = overlap / len(evidence_tokens) if evidence_tokens else 0.0
    return clamp01(0.85 * coverage + 0.15 * density)


def contradictory_evidence_ids(
    claim_text: str,
    evidence: list[EvidenceReference],
) -> list[str]:
    claim_lower = claim_text.lower()
    contradiction_markers = ("contraindicated", "avoid", "not recommended", "insufficient evidence")
    if not any(marker in claim_lower for marker in ("recommend", "should", "safe", "supports")):
        return []
    return [
        item.evidence_id
        for item in evidence
        if any(marker in item.text.lower() for marker in contradiction_markers)
    ]


def support_status(
    support_score: float,
    contradictory_ids: list[str],
) -> ClaimSupportStatus:
    if contradictory_ids:
        return ClaimSupportStatus.CONTRADICTED
    if support_score >= 0.70:
        return ClaimSupportStatus.SUPPORTED
    if support_score >= 0.35:
        return ClaimSupportStatus.PARTIALLY_SUPPORTED
    return ClaimSupportStatus.UNSUPPORTED


def calculate_citation_coverage(
    claims: list[ClaimToValidate],
    citation_allow_list: set[str],
) -> float:
    if not claims:
        return 1.0
    covered = 0
    for claim in claims:
        if claim.citation_ids and all(
            citation_id in citation_allow_list for citation_id in claim.citation_ids
        ):
            covered += 1
    return covered / len(claims)


def calculate_grounding_confidence(
    claim_results: list[ClaimGroundingResult],
    evidence: list[EvidenceReference],
) -> float:
    if not claim_results:
        return 0.0
    support = sum(result.support_score for result in claim_results) / len(claim_results)
    reliability = (
        sum(item.reliability_score for item in evidence) / len(evidence)
        if evidence
        else 0.0
    )
    return clamp01(0.70 * support + 0.30 * reliability)


def calculate_hallucination_risk(
    *,
    claim_results: list[ClaimGroundingResult],
    citation_coverage: float,
    grounding_confidence: float,
    upstream_confidence: float | None,
) -> float:
    if not claim_results:
        return 0.5
    unsupported_rate = sum(
        1
        for result in claim_results
        if result.status
        in {
            ClaimSupportStatus.UNSUPPORTED,
            ClaimSupportStatus.MISSING_CITATION,
            ClaimSupportStatus.INVALID_CITATION,
        }
    ) / len(claim_results)
    contradiction_rate = sum(
        1 for result in claim_results if result.status == ClaimSupportStatus.CONTRADICTED
    ) / len(claim_results)
    overconfidence_penalty = (
        0.15
        if upstream_confidence is not None
        and upstream_confidence >= 0.80
        and grounding_confidence < 0.60
        else 0.0
    )
    return clamp01(
        0.40 * unsupported_rate
        + 0.25 * contradiction_rate
        + 0.20 * (1.0 - citation_coverage)
        + 0.15 * (1.0 - grounding_confidence)
        + overconfidence_penalty
    )


def failed_validation_checks(
    claim_results: list[ClaimGroundingResult],
    citation_coverage: float,
    evidence: list[EvidenceReference],
) -> list[str]:
    checks: list[str] = []
    if not evidence:
        checks.append("evidence.empty")
    if citation_coverage < 1.0:
        checks.append("citation.coverage_incomplete")
    if any(result.status == ClaimSupportStatus.INVALID_CITATION for result in claim_results):
        checks.append("citation.invalid")
    if any(result.status == ClaimSupportStatus.MISSING_CITATION for result in claim_results):
        checks.append("citation.missing")
    if any(result.status == ClaimSupportStatus.UNSUPPORTED for result in claim_results):
        checks.append("claim.unsupported")
    if any(result.status == ClaimSupportStatus.CONTRADICTED for result in claim_results):
        checks.append("evidence.contradiction")
    return checks


def risk_band_from_score(score: float) -> HallucinationRiskBand:
    if score >= 0.80:
        return HallucinationRiskBand.CRITICAL
    if score >= 0.55:
        return HallucinationRiskBand.HIGH
    if score >= 0.25:
        return HallucinationRiskBand.MODERATE
    return HallucinationRiskBand.LOW


def escalation_recommendation(
    risk_band: HallucinationRiskBand,
    unsupported_claims: list[ClaimGroundingResult],
) -> EscalationRecommendation:
    if risk_band == HallucinationRiskBand.CRITICAL:
        return EscalationRecommendation.BLOCK
    if risk_band == HallucinationRiskBand.HIGH:
        return EscalationRecommendation.HUMAN_REVIEW
    if unsupported_claims:
        return EscalationRecommendation.QUALIFY
    return EscalationRecommendation.ALLOW


def observability_payload(
    request: HallucinationDetectionRequest,
    risk_score: float,
    risk_band: HallucinationRiskBand,
    grounding_confidence: float,
    citation_coverage: float,
    escalation: EscalationRecommendation,
    failed_checks: list[str],
) -> dict[str, Any]:
    return {
        "case_id": request.case_id,
        "workflow_id": request.workflow_id,
        "trace_id": request.trace_id,
        "claim_count": len(request.claims),
        "evidence_count": len(request.evidence),
        "hallucination_risk_score": risk_score,
        "risk_band": risk_band.value,
        "grounding_confidence": grounding_confidence,
        "citation_coverage": citation_coverage,
        "escalation_recommendation": escalation.value,
        "failed_checks": failed_checks,
    }


def claim_explanation(
    status: ClaimSupportStatus,
    support_score: float,
    contradictory_ids: list[str],
) -> str:
    if status == ClaimSupportStatus.CONTRADICTED:
        return f"Claim conflicts with retrieved evidence: {', '.join(contradictory_ids)}."
    if status == ClaimSupportStatus.SUPPORTED:
        return f"Claim is supported by cited evidence with support score {support_score:.2f}."
    if status == ClaimSupportStatus.PARTIALLY_SUPPORTED:
        return f"Claim is only partially supported; support score {support_score:.2f}."
    return f"Claim is not adequately supported; support score {support_score:.2f}."


def severity_from_report(report: HallucinationReport) -> RiskSeverity:
    return {
        HallucinationRiskBand.LOW: RiskSeverity.LOW,
        HallucinationRiskBand.MODERATE: RiskSeverity.MODERATE,
        HallucinationRiskBand.HIGH: RiskSeverity.HIGH,
        HallucinationRiskBand.CRITICAL: RiskSeverity.CRITICAL,
        HallucinationRiskBand.UNKNOWN: RiskSeverity.MODERATE,
    }[report.risk_band]


def clinical_tokens(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    stopwords = {
        "the", "and", "for", "with", "this", "that", "from", "into", "should",
        "may", "can", "are", "was", "were", "has", "have", "patient",
    }
    return {token for token in normalized.split() if len(token) > 2 and token not in stopwords}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
