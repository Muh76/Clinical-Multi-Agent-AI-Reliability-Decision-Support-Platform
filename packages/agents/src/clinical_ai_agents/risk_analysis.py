from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any

from clinical_ai_agents.contracts import (
    AgentFinding,
    AgentInput,
    AgentOutput,
    AgentRole,
    AgentRunStatus,
    ConfidenceBand,
    ConfidenceScore,
)
from clinical_ai_multimodal.patient_context.schemas import (
    LabValue,
    MedicationStatement,
    ModalityRecord,
    RawPatientContext,
    ValidationSeverity,
    VitalSign,
)
from clinical_ai_platform.observability import get_logger
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class RiskFactor(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str
    severity: RiskLevel
    message: str
    modality: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    uncertainty: str | None = None


class TrendSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    signal_id: str
    modality: str
    name: str
    direction: str
    first_value: float | None = None
    last_value: float | None = None
    unit: str | None = None
    observation_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str


class EscalationIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str
    level: RiskLevel
    message: str
    contributing_factors: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


class ContradictionSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str
    level: RiskLevel
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    explanation: str


class RiskAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    patient_id: str | None = None
    context_id: str | None = None
    risk_level: RiskLevel
    risk_score: float = Field(ge=0.0, le=1.0)
    contributing_factors: list[RiskFactor] = Field(default_factory=list)
    trend_signals: list[TrendSignal] = Field(default_factory=list)
    escalation_indicators: list[EscalationIndicator] = Field(default_factory=list)
    contradiction_signals: list[ContradictionSignal] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    uncertainty_metadata: dict[str, Any] = Field(default_factory=dict)
    explainability: dict[str, Any] = Field(default_factory=dict)


class RiskAnalysisAgent:
    name = "risk_analysis_agent"
    role = AgentRole.RISK_ANALYSIS

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started_at = datetime.now(UTC)
        start = perf_counter()
        logger.info(
            "agent_run_started",
            agent_name=self.name,
            agent_role=self.role.value,
            agent_run_id=agent_input.trace.agent_run_id,
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            case_id=agent_input.case_id,
        )
        try:
            report = analyze_risk(agent_input.payload)
            confidence = build_confidence(report)
            findings = agent_findings(report)
            status = (
                AgentRunStatus.REQUIRES_REVIEW
                if report.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
                or any(
                    indicator.requires_human_review
                    for indicator in report.escalation_indicators
                )
                else AgentRunStatus.COMPLETED
            )
            output = AgentOutput(
                case_id=agent_input.case_id,
                role=self.role,
                status=status,
                trace=agent_input.trace,
                summary=risk_summary(report),
                structured_payload={"risk_analysis": report.model_dump(mode="json")},
                findings=findings,
                confidence=confidence,
                citations=report.evidence_references,
                explainability=report.explainability,
                safety_hooks={
                    "requires_human_review": status == AgentRunStatus.REQUIRES_REVIEW,
                    "risk_level": report.risk_level.value,
                    "risk_score": report.risk_score,
                    "escalation_indicator_count": len(report.escalation_indicators),
                    "contradiction_count": len(report.contradiction_signals),
                    "diagnosis_generated": False,
                },
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception(
                "agent_run_failed",
                agent_name=self.name,
                agent_role=self.role.value,
                agent_run_id=agent_input.trace.agent_run_id,
                workflow_id=agent_input.trace.workflow_id,
                trace_id=agent_input.trace.trace_id,
                case_id=agent_input.case_id,
            )
            raise

        logger.info(
            "agent_run_completed",
            agent_name=self.name,
            agent_role=self.role.value,
            agent_run_id=agent_input.trace.agent_run_id,
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            case_id=agent_input.case_id,
            status=output.status.value,
            risk_level=report.risk_level.value,
            risk_score=report.risk_score,
            confidence_score=output.confidence.score,
            confidence_band=output.confidence.band.value,
            escalation_indicator_count=len(report.escalation_indicators),
            contradiction_count=len(report.contradiction_signals),
            latency_ms=round((perf_counter() - start) * 1000, 2),
        )
        return output


def analyze_risk(payload: dict[str, Any]) -> RiskAnalysisReport:
    raw_context = parse_patient_context(payload)
    patient_representation = parse_patient_representation(payload)
    evidence_items = parse_evidence_items(payload)
    evidence_refs = evidence_reference_ids(evidence_items)
    risk_factors = [
        *context_quality_factors(patient_representation),
        *vital_risk_factors(raw_context),
        *lab_risk_factors(raw_context),
        *medication_risk_factors(raw_context),
    ]
    trend_signals = temporal_trend_signals(raw_context)
    contradiction_signals = contradiction_detection(evidence_items)
    escalation_indicators = escalation_triggers(
        risk_factors=risk_factors,
        trend_signals=trend_signals,
        contradictions=contradiction_signals,
        evidence_refs=evidence_refs,
    )
    uncertainty = uncertainty_metadata(
        raw_context=raw_context,
        patient_representation=patient_representation,
        evidence_items=evidence_items,
        contradictions=contradiction_signals,
    )
    risk_score = aggregate_risk_score(
        risk_factors,
        trend_signals,
        escalation_indicators,
        contradiction_signals,
        uncertainty,
    )
    return RiskAnalysisReport(
        patient_id=(
            raw_context.patient_id
            if raw_context
            else patient_representation.get("patient_id")
        ),
        context_id=(
            raw_context.context_id
            if raw_context and raw_context.context_id
            else patient_representation.get("context_id")
        ),
        risk_level=risk_level_from_score(risk_score),
        risk_score=risk_score,
        contributing_factors=risk_factors,
        trend_signals=trend_signals,
        escalation_indicators=escalation_indicators,
        contradiction_signals=contradiction_signals,
        evidence_references=evidence_refs,
        uncertainty_metadata=uncertainty,
        explainability=explainability_metadata(
            risk_factors=risk_factors,
            trend_signals=trend_signals,
            escalation_indicators=escalation_indicators,
            contradiction_signals=contradiction_signals,
        ),
    )


def parse_patient_context(payload: dict[str, Any]) -> RawPatientContext | None:
    context_payload = (
        payload.get("patient_context")
        or payload.get("raw_patient_context")
        or payload.get("structured_patient_context", {}).get("normalized")
    )
    if context_payload is None:
        return None
    return RawPatientContext.model_validate(context_payload)


def parse_patient_representation(payload: dict[str, Any]) -> dict[str, Any]:
    return (
        payload.get("patient_representation")
        or payload.get("patient_context_agent_output", {}).get("patient_representation")
        or {}
    )


def parse_evidence_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    package = (
        payload.get("evidence_package")
        or payload.get("evidence_retrieval")
        or payload.get("evidence_retrieval_agent_output", {}).get("evidence_package")
        or {}
    )
    evidence = package.get("evidence", payload.get("evidence", []))
    return [item for item in evidence if isinstance(item, dict)]


def context_quality_factors(patient_representation: dict[str, Any]) -> list[RiskFactor]:
    factors: list[RiskFactor] = []
    missingness = patient_representation.get("missingness_summary", {})
    absent_modalities = missingness.get("absent_modalities", [])
    if absent_modalities:
        factors.append(
            RiskFactor(
                code="context.absent_modalities",
                severity=RiskLevel.MODERATE,
                message=f"Absent modalities: {', '.join(map(str, absent_modalities))}.",
                uncertainty="Missing modalities reduce confidence in downstream risk analysis.",
            )
        )
    for finding in patient_representation.get("validation_findings", []):
        severity = RiskLevel.HIGH if finding.get("severity") == "error" else RiskLevel.MODERATE
        factors.append(
            RiskFactor(
                code=str(finding.get("code", "context.validation_finding")),
                severity=severity,
                message=str(finding.get("message", "Patient context validation finding.")),
                modality=str(finding.get("modality")) if finding.get("modality") else None,
                source_refs=[str(finding.get("field_path"))] if finding.get("field_path") else [],
            )
        )
    return factors


def vital_risk_factors(context: RawPatientContext | None) -> list[RiskFactor]:
    if context is None:
        return []
    factors: list[RiskFactor] = []
    for index, vital in enumerate(context.vitals):
        if vital.value is None:
            continue
        name = vital.name.lower()
        value = vital.value.value
        unit = vital.value.unit
        source_ref = f"vitals[{index}]"
        if "heart" in name and unit == "beats/min":
            if value >= 130 or value <= 40:
                factors.append(high_factor("vital.heart_rate_extreme", vital.name, source_ref))
            elif value >= 110 or value <= 50:
                factors.append(moderate_factor("vital.heart_rate_unstable", vital.name, source_ref))
        if "oxygen" in name and unit == "%":
            if value < 90:
                factors.append(high_factor("vital.oxygen_saturation_low", vital.name, source_ref))
            elif value < 94:
                factors.append(
                    moderate_factor("vital.oxygen_saturation_borderline", vital.name, source_ref)
                )
        if "temperature" in name:
            if value >= 39.0 or value < 35.0:
                factors.append(high_factor("vital.temperature_extreme", vital.name, source_ref))
            elif value >= 38.0:
                factors.append(
                    moderate_factor("vital.temperature_elevated", vital.name, source_ref)
                )
        if "systolic" in name and value < 90:
            factors.append(high_factor("vital.systolic_bp_low", vital.name, source_ref))
    return factors


def lab_risk_factors(context: RawPatientContext | None) -> list[RiskFactor]:
    if context is None:
        return []
    factors: list[RiskFactor] = []
    for index, lab in enumerate(context.labs):
        if lab.value is None:
            continue
        name = lab.test_name.lower()
        value = lab.value.value
        source_ref = f"labs[{index}]"
        if "lactate" in name and value >= 4:
            factors.append(high_factor("lab.lactate_high", lab.test_name, source_ref))
        elif "lactate" in name and value >= 2:
            factors.append(moderate_factor("lab.lactate_elevated", lab.test_name, source_ref))
        if "creatinine" in name and value >= 2:
            factors.append(moderate_factor("lab.creatinine_elevated", lab.test_name, source_ref))
        if "potassium" in name and (value >= 6.0 or value <= 2.8):
            factors.append(high_factor("lab.potassium_extreme", lab.test_name, source_ref))
    return factors


def medication_risk_factors(context: RawPatientContext | None) -> list[RiskFactor]:
    if context is None:
        return []
    factors: list[RiskFactor] = []
    for index, medication in enumerate(context.medications):
        name = medication.medication_name.lower()
        if any(term in name for term in ("vancomycin", "gentamicin", "amikacin")):
            factors.append(
                RiskFactor(
                    code="medication.monitoring_sensitive",
                    severity=RiskLevel.MODERATE,
                    message=(
                        f"Medication '{medication.medication_name}' may require context-aware "
                        "monitoring evidence."
                    ),
                    modality="medications",
                    source_refs=[f"medications[{index}]"],
                    uncertainty="Risk depends on indication, renal function, dosing, and timing.",
                )
            )
    return factors


def temporal_trend_signals(context: RawPatientContext | None) -> list[TrendSignal]:
    if context is None:
        return []
    records: dict[tuple[str, str], list[VitalSign | LabValue]] = defaultdict(list)
    for vital in context.vitals:
        if vital.value is not None:
            records[("vitals", vital.name.lower())].append(vital)
    for lab in context.labs:
        if lab.value is not None:
            records[("labs", lab.test_name.lower())].append(lab)

    signals: list[TrendSignal] = []
    for (modality, name), grouped_records in records.items():
        ordered = sorted(grouped_records, key=record_time)
        if len(ordered) < 2:
            continue
        first = ordered[0].value
        last = ordered[-1].value
        if first is None or last is None:
            continue
        delta = last.value - first.value
        if abs(delta) < max(abs(first.value) * 0.10, 0.5):
            direction = "stable"
        elif delta > 0:
            direction = "increasing"
        else:
            direction = "decreasing"
        signals.append(
            TrendSignal(
                signal_id=f"{modality}.{name}.trend",
                modality=modality,
                name=name,
                direction=direction,
                first_value=first.value,
                last_value=last.value,
                unit=last.unit,
                observation_count=len(ordered),
                confidence=trend_confidence(ordered),
                explanation=(
                    f"{name} is {direction} across {len(ordered)} timestamped observations."
                ),
            )
        )
    return signals


def contradiction_detection(evidence_items: list[dict[str, Any]]) -> list[ContradictionSignal]:
    positive_refs: list[str] = []
    caution_refs: list[str] = []
    negative_refs: list[str] = []
    for item in evidence_items:
        text = str(item.get("text", "")).lower()
        ref = str(item.get("citation_id") or item.get("source_id") or item.get("chunk_id"))
        if any(term in text for term in ("contraindicated", "avoid", "not recommended")):
            negative_refs.append(ref)
        if any(term in text for term in ("recommend", "recommended", "should")):
            positive_refs.append(ref)
        if any(term in text for term in ("limited evidence", "uncertain", "insufficient evidence")):
            caution_refs.append(ref)
    signals: list[ContradictionSignal] = []
    if positive_refs and negative_refs:
        signals.append(
            ContradictionSignal(
                code="evidence.recommendation_conflict",
                level=RiskLevel.HIGH,
                message="Retrieved evidence contains both recommendation and avoidance language.",
                evidence_refs=sorted(set([*positive_refs, *negative_refs])),
                explanation=(
                    "Evidence conflict should be reviewed before downstream recommendations."
                ),
            )
        )
    if caution_refs:
        signals.append(
            ContradictionSignal(
                code="evidence.uncertainty_language",
                level=RiskLevel.MODERATE,
                message="Retrieved evidence contains uncertainty or limited-evidence language.",
                evidence_refs=sorted(set(caution_refs)),
                explanation=(
                    "Uncertainty language should lower confidence and trigger qualification."
                ),
            )
        )
    return signals


def escalation_triggers(
    *,
    risk_factors: list[RiskFactor],
    trend_signals: list[TrendSignal],
    contradictions: list[ContradictionSignal],
    evidence_refs: list[str],
) -> list[EscalationIndicator]:
    indicators: list[EscalationIndicator] = []
    high_factor_codes = [
        factor.code
        for factor in risk_factors
        if factor.severity in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    ]
    if high_factor_codes:
        indicators.append(
            EscalationIndicator(
                code="risk.high_factor_present",
                level=RiskLevel.HIGH,
                message="High-severity risk factors are present in structured context.",
                contributing_factors=high_factor_codes,
                evidence_refs=evidence_refs,
                requires_human_review=True,
            )
        )
    unstable_trends = [
        signal.signal_id
        for signal in trend_signals
        if signal.direction in {"increasing", "decreasing"} and signal.confidence >= 0.65
    ]
    if unstable_trends:
        indicators.append(
            EscalationIndicator(
                code="risk.unstable_trend_present",
                level=RiskLevel.MODERATE,
                message="Temporal trends indicate changing patient context.",
                contributing_factors=unstable_trends,
                evidence_refs=evidence_refs,
                requires_human_review=False,
            )
        )
    if any(signal.level == RiskLevel.HIGH for signal in contradictions):
        indicators.append(
            EscalationIndicator(
                code="risk.evidence_contradiction_present",
                level=RiskLevel.HIGH,
                message="Contradictory evidence should be reviewed before downstream use.",
                contributing_factors=[signal.code for signal in contradictions],
                evidence_refs=evidence_refs,
                requires_human_review=True,
            )
        )
    return indicators


def uncertainty_metadata(
    *,
    raw_context: RawPatientContext | None,
    patient_representation: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    contradictions: list[ContradictionSignal],
) -> dict[str, Any]:
    missingness = patient_representation.get("missingness_summary", {})
    absent_modalities = missingness.get("absent_modalities", [])
    event_count = len(raw_context.vitals) + len(raw_context.labs) if raw_context else 0
    timestamped = 0
    if raw_context:
        timestamped = sum(
            1
            for record in [*raw_context.vitals, *raw_context.labs, *raw_context.medications]
            if record.temporal.observed_at or record.temporal.recorded_at
        )
    return {
        "absent_modalities": absent_modalities,
        "missing_field_count": missingness.get("missing_field_count", 0),
        "evidence_count": len(evidence_items),
        "contradiction_count": len(contradictions),
        "timestamped_context_fraction": timestamped / event_count if event_count else 0.0,
        "limitations": uncertainty_limitations(absent_modalities, evidence_items, contradictions),
    }


def aggregate_risk_score(
    risk_factors: list[RiskFactor],
    trend_signals: list[TrendSignal],
    escalation_indicators: list[EscalationIndicator],
    contradiction_signals: list[ContradictionSignal],
    uncertainty: dict[str, Any],
) -> float:
    factor_score = sum(risk_weight(factor.severity) for factor in risk_factors)
    trend_score = sum(0.08 for signal in trend_signals if signal.direction != "stable")
    escalation_score = sum(risk_weight(indicator.level) for indicator in escalation_indicators)
    contradiction_score = sum(risk_weight(signal.level) for signal in contradiction_signals)
    uncertainty_score = 0.04 * len(uncertainty.get("absent_modalities", []))
    return clamp01(
        factor_score
        + trend_score
        + escalation_score
        + contradiction_score
        + uncertainty_score
    )


def risk_weight(level: RiskLevel) -> float:
    return {
        RiskLevel.LOW: 0.03,
        RiskLevel.MODERATE: 0.10,
        RiskLevel.HIGH: 0.22,
        RiskLevel.CRITICAL: 0.35,
        RiskLevel.UNKNOWN: 0.0,
    }[level]


def risk_level_from_score(score: float) -> RiskLevel:
    if score >= 0.80:
        return RiskLevel.CRITICAL
    if score >= 0.50:
        return RiskLevel.HIGH
    if score >= 0.20:
        return RiskLevel.MODERATE
    if score > 0:
        return RiskLevel.LOW
    return RiskLevel.UNKNOWN


def explainability_metadata(
    *,
    risk_factors: list[RiskFactor],
    trend_signals: list[TrendSignal],
    escalation_indicators: list[EscalationIndicator],
    contradiction_signals: list[ContradictionSignal],
) -> dict[str, Any]:
    return {
        "top_factor_codes": [factor.code for factor in risk_factors[:10]],
        "trend_signal_ids": [signal.signal_id for signal in trend_signals],
        "escalation_codes": [indicator.code for indicator in escalation_indicators],
        "contradiction_codes": [signal.code for signal in contradiction_signals],
        "analysis_boundary": "risk-oriented reliability analysis; no diagnosis generated",
    }


def build_confidence(report: RiskAnalysisReport) -> ConfidenceScore:
    evidence_score = min(1.0, len(report.evidence_references) / 3)
    trend_score = (
        sum(signal.confidence for signal in report.trend_signals) / len(report.trend_signals)
        if report.trend_signals
        else 0.35
    )
    uncertainty_penalty = min(0.4, 0.08 * len(report.uncertainty_metadata.get("limitations", [])))
    contradiction_penalty = 0.15 if report.contradiction_signals else 0.0
    context_score = 1.0 - min(
        0.5,
        0.08 * len(report.uncertainty_metadata.get("absent_modalities", [])),
    )
    score = clamp01(
        0.30 * context_score
        + 0.25 * evidence_score
        + 0.25 * trend_score
        + 0.20 * (1.0 - uncertainty_penalty - contradiction_penalty)
    )
    return ConfidenceScore(
        score=score,
        band=confidence_band(score),
        components={
            "context_completeness": context_score,
            "evidence_support": evidence_score,
            "trend_confidence": trend_score,
            "uncertainty_penalty": uncertainty_penalty,
            "contradiction_penalty": contradiction_penalty,
        },
        rationale=confidence_rationale(score, report),
    )


def agent_findings(report: RiskAnalysisReport) -> list[AgentFinding]:
    return [
        AgentFinding(
            code=factor.code,
            severity=factor.severity.value,
            message=factor.message,
            evidence_refs=factor.evidence_refs or factor.source_refs,
            requires_human_review=factor.severity in {RiskLevel.HIGH, RiskLevel.CRITICAL},
        )
        for factor in report.contributing_factors
    ] + [
        AgentFinding(
            code=indicator.code,
            severity=indicator.level.value,
            message=indicator.message,
            evidence_refs=indicator.evidence_refs,
            requires_human_review=indicator.requires_human_review,
        )
        for indicator in report.escalation_indicators
    ]


def record_time(record: ModalityRecord) -> datetime:
    return (
        record.temporal.observed_at
        or record.temporal.recorded_at
        or datetime.max.replace(tzinfo=UTC)
    )


def trend_confidence(records: list[VitalSign | LabValue]) -> float:
    timestamped = sum(
        1 for record in records if record.temporal.observed_at or record.temporal.recorded_at
    )
    return clamp01(0.35 + 0.15 * min(len(records), 4) + 0.25 * (timestamped / len(records)))


def evidence_reference_ids(evidence_items: list[dict[str, Any]]) -> list[str]:
    refs = [
        str(item.get("citation_id") or item.get("source_id") or item.get("chunk_id"))
        for item in evidence_items
        if item.get("citation_id") or item.get("source_id") or item.get("chunk_id")
    ]
    return sorted(set(refs))


def uncertainty_limitations(
    absent_modalities: list[Any],
    evidence_items: list[dict[str, Any]],
    contradictions: list[ContradictionSignal],
) -> list[str]:
    limitations: list[str] = []
    if absent_modalities:
        limitations.append("Some modalities are absent from structured context.")
    if not evidence_items:
        limitations.append("No retrieved evidence was supplied to risk analysis.")
    if contradictions:
        limitations.append("Retrieved evidence contains contradiction or uncertainty signals.")
    return limitations


def high_factor(code: str, label: str, source_ref: str) -> RiskFactor:
    return RiskFactor(
        code=code,
        severity=RiskLevel.HIGH,
        message=f"High-severity risk signal detected for {label}.",
        source_refs=[source_ref],
    )


def moderate_factor(code: str, label: str, source_ref: str) -> RiskFactor:
    return RiskFactor(
        code=code,
        severity=RiskLevel.MODERATE,
        message=f"Moderate risk signal detected for {label}.",
        source_refs=[source_ref],
    )


def confidence_band(score: float) -> ConfidenceBand:
    if score >= 0.85:
        return ConfidenceBand.HIGH
    if score >= 0.65:
        return ConfidenceBand.MODERATE
    if score > 0.0:
        return ConfidenceBand.LOW
    return ConfidenceBand.UNKNOWN


def confidence_rationale(score: float, report: RiskAnalysisReport) -> str:
    if report.contradiction_signals:
        return "Risk analysis includes evidence contradiction signals; confidence is reduced."
    if score >= 0.85:
        return "Risk analysis has strong context, evidence support, and temporal confidence."
    if score >= 0.65:
        return "Risk analysis is usable with some uncertainty or incomplete evidence."
    return "Risk analysis has limited support; downstream systems should request review."


def risk_summary(report: RiskAnalysisReport) -> str:
    return (
        f"Risk-oriented reliability analysis completed with level {report.risk_level.value}. "
        f"Contributing factors: {len(report.contributing_factors)}. "
        f"Escalation indicators: {len(report.escalation_indicators)}. "
        "No diagnosis was generated."
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
