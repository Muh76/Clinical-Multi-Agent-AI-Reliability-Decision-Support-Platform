from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from clinical_ai_safety.hallucination import EscalationRecommendation, clamp01


class UncertaintyBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class UncertaintySourceType(StrEnum):
    RETRIEVAL = "retrieval"
    GROUNDING = "grounding"
    MODALITY_COMPLETENESS = "modality_completeness"
    RISK_STABILITY = "risk_stability"
    CONTRADICTION = "contradiction"
    TEMPORAL_CONSISTENCY = "temporal_consistency"
    DATA_QUALITY = "data_quality"


class ReliabilityIndicatorStatus(StrEnum):
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    WEAK = "weak"
    MISSING = "missing"


class UncertaintyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ModalityCompletenessInput(UncertaintyModel):
    modality: str
    present: bool
    required: bool = True
    record_count: int = Field(default=0, ge=0)
    missing_field_count: int = Field(default=0, ge=0)
    quality_issue_count: int = Field(default=0, ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class UncertaintyComponent(UncertaintyModel):
    source_type: UncertaintySourceType
    confidence_score: float = Field(ge=0.0, le=1.0)
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    rationale: str
    contributing_factors: list[str] = Field(default_factory=list)


class ReliabilityIndicator(UncertaintyModel):
    code: str
    status: ReliabilityIndicatorStatus
    score: float = Field(ge=0.0, le=1.0)
    message: str


class UncertaintyScoringRequest(UncertaintyModel):
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    retrieval_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    grounding_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    verification_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    source_trust_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_analysis_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_factor_count: int = Field(default=0, ge=0)
    unstable_trend_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    temporal_completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    temporal_inconsistency_count: int = Field(default=0, ge=0)
    modality_inputs: list[ModalityCompletenessInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UncertaintyReport(UncertaintyModel):
    report_id: str
    case_id: str
    workflow_id: str | None = None
    trace_id: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    uncertainty_band: UncertaintyBand
    components: list[UncertaintyComponent] = Field(default_factory=list)
    uncertainty_sources: list[str] = Field(default_factory=list)
    reliability_indicators: list[ReliabilityIndicator] = Field(default_factory=list)
    escalation_recommendation: EscalationRecommendation
    calibration_notes: list[str] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UncertaintyScoringEngine:
    async def score(self, request: UncertaintyScoringRequest) -> UncertaintyReport:
        return score_uncertainty(request)


def score_uncertainty(request: UncertaintyScoringRequest) -> UncertaintyReport:
    components = [
        retrieval_component(request),
        grounding_component(request),
        modality_component(request),
        risk_stability_component(request),
        contradiction_component(request),
        temporal_component(request),
    ]
    confidence_score = aggregate_confidence(components)
    uncertainty_score = clamp01(1.0 - confidence_score)
    uncertainty_band = uncertainty_band_from_score(uncertainty_score)
    uncertainty_sources = source_codes(components)
    reliability_indicators = build_reliability_indicators(request, components)
    escalation = uncertainty_escalation(
        uncertainty_band=uncertainty_band,
        request=request,
        uncertainty_sources=uncertainty_sources,
    )
    return UncertaintyReport(
        report_id=f"uncertainty-report-{uuid4()}",
        case_id=request.case_id,
        workflow_id=request.workflow_id,
        trace_id=request.trace_id,
        confidence_score=confidence_score,
        uncertainty_score=uncertainty_score,
        uncertainty_band=uncertainty_band,
        components=components,
        uncertainty_sources=uncertainty_sources,
        reliability_indicators=reliability_indicators,
        escalation_recommendation=escalation,
        calibration_notes=calibration_notes(request, components),
        observability=uncertainty_observability_payload(
            request=request,
            confidence_score=confidence_score,
            uncertainty_score=uncertainty_score,
            uncertainty_band=uncertainty_band,
            uncertainty_sources=uncertainty_sources,
            escalation=escalation,
        ),
    )


def retrieval_component(request: UncertaintyScoringRequest) -> UncertaintyComponent:
    score = request.retrieval_confidence if request.retrieval_confidence is not None else 0.35
    factors = [] if request.retrieval_confidence is not None else ["retrieval_confidence_missing"]
    return component(
        source_type=UncertaintySourceType.RETRIEVAL,
        confidence_score=score,
        weight=0.18,
        rationale="Retrieval confidence estimates whether the evidence set is adequate.",
        factors=factors,
    )


def grounding_component(request: UncertaintyScoringRequest) -> UncertaintyComponent:
    scores = [
        value
        for value in (
            request.grounding_confidence,
            request.verification_confidence,
            request.citation_coverage,
            request.evidence_coverage,
            request.source_trust_score,
        )
        if value is not None
    ]
    score = sum(scores) / len(scores) if scores else 0.30
    factors = [] if scores else ["grounding_signals_missing"]
    if request.citation_coverage is not None and request.citation_coverage < 1.0:
        factors.append("citation_coverage_incomplete")
    if request.source_trust_score is not None and request.source_trust_score < 0.60:
        factors.append("source_trust_low")
    return component(
        source_type=UncertaintySourceType.GROUNDING,
        confidence_score=score,
        weight=0.24,
        rationale="Grounding confidence combines citation, evidence support, and source trust.",
        factors=factors,
    )


def modality_component(request: UncertaintyScoringRequest) -> UncertaintyComponent:
    score = modality_completeness_score(request.modality_inputs)
    factors = modality_uncertainty_factors(request.modality_inputs)
    return component(
        source_type=UncertaintySourceType.MODALITY_COMPLETENESS,
        confidence_score=score,
        weight=0.16,
        rationale="Modality completeness estimates whether required patient context is present.",
        factors=factors,
    )


def risk_stability_component(request: UncertaintyScoringRequest) -> UncertaintyComponent:
    base = (
        request.risk_analysis_confidence
        if request.risk_analysis_confidence is not None
        else 0.45
    )
    trend_penalty = min(0.25, 0.05 * request.unstable_trend_count)
    factor_penalty = min(0.20, 0.02 * request.risk_factor_count)
    score = clamp01(base - trend_penalty - factor_penalty)
    factors: list[str] = []
    if request.risk_analysis_confidence is None:
        factors.append("risk_analysis_confidence_missing")
    if request.unstable_trend_count:
        factors.append("unstable_trends_present")
    return component(
        source_type=UncertaintySourceType.RISK_STABILITY,
        confidence_score=score,
        weight=0.14,
        rationale="Risk stability falls when risk factors or unstable trends accumulate.",
        factors=factors,
    )


def contradiction_component(request: UncertaintyScoringRequest) -> UncertaintyComponent:
    score = clamp01(1.0 - min(0.70, 0.25 * request.contradiction_count))
    factors = ["contradictions_present"] if request.contradiction_count else []
    return component(
        source_type=UncertaintySourceType.CONTRADICTION,
        confidence_score=score,
        weight=0.18,
        rationale="Contradictory evidence or reasoning materially increases uncertainty.",
        factors=factors,
    )


def temporal_component(request: UncertaintyScoringRequest) -> UncertaintyComponent:
    base = request.temporal_completeness if request.temporal_completeness is not None else 0.40
    inconsistency_penalty = min(0.45, 0.12 * request.temporal_inconsistency_count)
    score = clamp01(base - inconsistency_penalty)
    factors: list[str] = []
    if request.temporal_completeness is None:
        factors.append("temporal_completeness_missing")
    if request.temporal_inconsistency_count:
        factors.append("temporal_inconsistencies_present")
    return component(
        source_type=UncertaintySourceType.TEMPORAL_CONSISTENCY,
        confidence_score=score,
        weight=0.10,
        rationale="Temporal confidence reflects timestamp completeness and consistency.",
        factors=factors,
    )


def component(
    *,
    source_type: UncertaintySourceType,
    confidence_score: float,
    weight: float,
    rationale: str,
    factors: list[str],
) -> UncertaintyComponent:
    score = clamp01(confidence_score)
    return UncertaintyComponent(
        source_type=source_type,
        confidence_score=score,
        uncertainty_score=clamp01(1.0 - score),
        weight=weight,
        rationale=rationale,
        contributing_factors=factors,
    )


def modality_completeness_score(inputs: list[ModalityCompletenessInput]) -> float:
    if not inputs:
        return 0.0
    weighted_scores: list[float] = []
    for item in inputs:
        if not item.required and not item.present:
            weighted_scores.append(1.0)
            continue
        presence_score = 1.0 if item.present else 0.0
        volume_score = min(1.0, item.record_count / 3) if item.present else 0.0
        quality_score = clamp01(
            1.0 - 0.07 * item.missing_field_count - 0.12 * item.quality_issue_count
        )
        explicit_confidence = item.confidence if item.confidence is not None else quality_score
        weighted_scores.append(
            clamp01(
                0.40 * presence_score
                + 0.25 * volume_score
                + 0.20 * quality_score
                + 0.15 * explicit_confidence
            )
        )
    return sum(weighted_scores) / len(weighted_scores)


def modality_uncertainty_factors(inputs: list[ModalityCompletenessInput]) -> list[str]:
    if not inputs:
        return ["modality_inputs_missing"]
    factors: list[str] = []
    for item in inputs:
        if item.required and not item.present:
            factors.append(f"modality_absent:{item.modality}")
        elif item.missing_field_count:
            factors.append(f"modality_missing_fields:{item.modality}")
        if item.quality_issue_count:
            factors.append(f"modality_quality_issues:{item.modality}")
    return factors


def aggregate_confidence(components: list[UncertaintyComponent]) -> float:
    weight_sum = sum(component.weight for component in components)
    if weight_sum == 0:
        return 0.0
    score = sum(
        component.confidence_score * component.weight for component in components
    ) / weight_sum
    return clamp01(score)


def uncertainty_band_from_score(score: float) -> UncertaintyBand:
    if score >= 0.80:
        return UncertaintyBand.CRITICAL
    if score >= 0.55:
        return UncertaintyBand.HIGH
    if score >= 0.30:
        return UncertaintyBand.MODERATE
    return UncertaintyBand.LOW


def source_codes(components: list[UncertaintyComponent]) -> list[str]:
    return [
        component.source_type.value
        for component in components
        if component.uncertainty_score >= 0.35 or component.contributing_factors
    ]


def build_reliability_indicators(
    request: UncertaintyScoringRequest,
    components: list[UncertaintyComponent],
) -> list[ReliabilityIndicator]:
    indicators = [
        ReliabilityIndicator(
            code=f"uncertainty.{component.source_type.value}",
            status=indicator_status(component.confidence_score),
            score=component.confidence_score,
            message=component.rationale,
        )
        for component in components
    ]
    if request.contradiction_count:
        indicators.append(
            ReliabilityIndicator(
                code="safety.contradiction_presence",
                status=ReliabilityIndicatorStatus.WEAK,
                score=clamp01(1.0 - 0.25 * request.contradiction_count),
                message="Contradictions require qualification, review, or blocking.",
            )
        )
    return indicators


def indicator_status(score: float) -> ReliabilityIndicatorStatus:
    if score >= 0.80:
        return ReliabilityIndicatorStatus.STRONG
    if score >= 0.60:
        return ReliabilityIndicatorStatus.ACCEPTABLE
    if score > 0.0:
        return ReliabilityIndicatorStatus.WEAK
    return ReliabilityIndicatorStatus.MISSING


def uncertainty_escalation(
    *,
    uncertainty_band: UncertaintyBand,
    request: UncertaintyScoringRequest,
    uncertainty_sources: list[str],
) -> EscalationRecommendation:
    if uncertainty_band == UncertaintyBand.CRITICAL or request.contradiction_count >= 2:
        return EscalationRecommendation.BLOCK
    if uncertainty_band == UncertaintyBand.HIGH or request.contradiction_count:
        return EscalationRecommendation.HUMAN_REVIEW
    if uncertainty_sources:
        return EscalationRecommendation.QUALIFY
    return EscalationRecommendation.ALLOW


def calibration_notes(
    request: UncertaintyScoringRequest,
    components: list[UncertaintyComponent],
) -> list[str]:
    notes = [
        "Scores should be calibrated against labeled retrieval, grounding, and safety outcomes.",
        "Confidence is not a probability of clinical correctness without calibration.",
    ]
    if request.contradiction_count:
        notes.append(
            "Contradiction outcomes should be monitored separately from average confidence."
        )
    if any(component.confidence_score < 0.50 for component in components):
        notes.append("Low component scores should trigger component-specific reliability review.")
    return notes


def uncertainty_observability_payload(
    *,
    request: UncertaintyScoringRequest,
    confidence_score: float,
    uncertainty_score: float,
    uncertainty_band: UncertaintyBand,
    uncertainty_sources: list[str],
    escalation: EscalationRecommendation,
) -> dict[str, Any]:
    return {
        "case_id": request.case_id,
        "workflow_id": request.workflow_id,
        "trace_id": request.trace_id,
        "confidence_score": confidence_score,
        "uncertainty_score": uncertainty_score,
        "uncertainty_band": uncertainty_band.value,
        "uncertainty_sources": uncertainty_sources,
        "escalation_recommendation": escalation.value,
        "contradiction_count": request.contradiction_count,
        "temporal_inconsistency_count": request.temporal_inconsistency_count,
        "modality_count": len(request.modality_inputs),
    }
