"""Safety validation package."""

from clinical_ai_safety.hallucination import (
    ClaimGroundingResult,
    ClaimSupportStatus,
    ClaimToValidate,
    EscalationRecommendation,
    EvidenceReference,
    HallucinationDetectionEngine,
    HallucinationDetectionRequest,
    HallucinationReport,
    HallucinationRiskBand,
    evaluate_hallucination_risk,
    severity_from_report,
)

__all__ = [
    "ClaimGroundingResult",
    "ClaimSupportStatus",
    "ClaimToValidate",
    "EscalationRecommendation",
    "EvidenceReference",
    "HallucinationDetectionEngine",
    "HallucinationDetectionRequest",
    "HallucinationReport",
    "HallucinationRiskBand",
    "evaluate_hallucination_risk",
    "severity_from_report",
]

