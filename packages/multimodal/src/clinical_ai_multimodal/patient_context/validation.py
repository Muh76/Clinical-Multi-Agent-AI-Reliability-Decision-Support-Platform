from clinical_ai_multimodal.patient_context.schemas import (
    LabValue,
    ModalityType,
    RawPatientContext,
    ValidationFinding,
    ValidationSeverity,
    VitalSign,
)


def validate_patient_context(context: RawPatientContext) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if context.demographics is None:
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.WARNING,
                code="demographics.missing",
                message=(
                    "Demographics are absent; downstream risk stratification should treat "
                    "cohort features as unavailable."
                ),
                modality=ModalityType.DEMOGRAPHICS,
            )
        )

    modality_counts = {
        ModalityType.VITALS: len(context.vitals),
        ModalityType.LABS: len(context.labs),
        ModalityType.MEDICATIONS: len(context.medications),
        ModalityType.CLINICAL_NOTES: len(context.clinical_notes),
        ModalityType.IMAGING_METADATA: len(context.imaging_metadata),
    }
    for modality, count in modality_counts.items():
        if count == 0:
            findings.append(
                ValidationFinding(
                    severity=ValidationSeverity.INFO,
                    code=f"{modality}.empty",
                    message=f"No {modality.value.replace('_', ' ')} records were supplied.",
                    modality=modality,
                )
            )

    for index, vital in enumerate(context.vitals):
        findings.extend(validate_vital(vital, index))
    for index, lab in enumerate(context.labs):
        findings.extend(validate_lab(lab, index))

    return findings


def validate_vital(vital: VitalSign, index: int) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if vital.value is None:
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.WARNING,
                code="vital.value_missing",
                message=f"Vital sign '{vital.name}' has no numeric value.",
                modality=ModalityType.VITALS,
                field_path=f"vitals[{index}].value",
            )
        )
        return findings

    name = vital.name.lower()
    value = vital.value.value
    unit = vital.value.unit
    if "heart" in name and unit == "beats/min" and not 20 <= value <= 250:
        findings.append(out_of_range("vital.implausible_heart_rate", vital.name, index))
    if "temperature" in name and unit == "Cel" and not 25 <= value <= 45:
        findings.append(out_of_range("vital.implausible_temperature", vital.name, index))
    if "oxygen" in name and unit == "%" and not 0 <= value <= 100:
        findings.append(out_of_range("vital.implausible_oxygen_saturation", vital.name, index))
    return findings


def validate_lab(lab: LabValue, index: int) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if lab.value is None:
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.WARNING,
                code="lab.value_missing",
                message=f"Lab value '{lab.test_name}' has no numeric value.",
                modality=ModalityType.LABS,
                field_path=f"labs[{index}].value",
            )
        )
        return findings
    if lab.reference_range is None:
        return findings
    low = lab.reference_range.low
    high = lab.reference_range.high
    if low is not None and lab.value.value < low:
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.INFO,
                code="lab.below_reference_range",
                message=f"Lab value '{lab.test_name}' is below the provided reference range.",
                modality=ModalityType.LABS,
                field_path=f"labs[{index}].value",
            )
        )
    if high is not None and lab.value.value > high:
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.INFO,
                code="lab.above_reference_range",
                message=f"Lab value '{lab.test_name}' is above the provided reference range.",
                modality=ModalityType.LABS,
                field_path=f"labs[{index}].value",
            )
        )
    return findings


def out_of_range(code: str, label: str, index: int) -> ValidationFinding:
    return ValidationFinding(
        severity=ValidationSeverity.ERROR,
        code=code,
        message=f"Vital sign '{label}' has an implausible normalized value.",
        modality=ModalityType.VITALS,
        field_path=f"vitals[{index}].value",
    )
