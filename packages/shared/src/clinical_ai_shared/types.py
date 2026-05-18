from enum import StrEnum


class ClinicalEvidenceLevel(StrEnum):
    GUIDELINE = "guideline"
    SYSTEMATIC_REVIEW = "systematic_review"
    PRIMARY_STUDY = "primary_study"
    LOCAL_POLICY = "local_policy"
    EXPERT_CONSENSUS = "expert_consensus"


class RiskSeverity(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

