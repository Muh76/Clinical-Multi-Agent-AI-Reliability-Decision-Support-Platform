from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ModalityType(StrEnum):
    VITALS = "vitals"
    LABS = "labs"
    MEDICATIONS = "medications"
    DEMOGRAPHICS = "demographics"
    CLINICAL_NOTES = "clinical_notes"
    IMAGING_METADATA = "imaging_metadata"


class MissingnessReason(StrEnum):
    NOT_PROVIDED = "not_provided"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    REDACTED = "redacted"
    SOURCE_ERROR = "source_error"


class ValidationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TemporalRelation(StrEnum):
    BEFORE_ENCOUNTER = "before_encounter"
    DURING_ENCOUNTER = "during_encounter"
    AFTER_ENCOUNTER = "after_encounter"
    UNKNOWN = "unknown"


class PatientContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceProvenance(PatientContextModel):
    source_system: str = Field(
        description="Originating EHR, device, registry, or ingestion adapter."
    )
    source_record_id: str | None = None
    ingestion_id: str | None = None
    received_at: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("received_at")
    @classmethod
    def normalize_received_at(cls, value: datetime | None) -> datetime | None:
        return ensure_aware_datetime(value)


class MissingValueMarker(PatientContextModel):
    field_name: str
    reason: MissingnessReason = MissingnessReason.UNKNOWN
    detail: str | None = None


class ValidationFinding(PatientContextModel):
    severity: ValidationSeverity
    code: str
    message: str
    modality: ModalityType | None = None
    field_path: str | None = None


class NormalizedQuantity(PatientContextModel):
    value: float
    unit: str
    original_value: str | float | int | None = None
    original_unit: str | None = None


class ReferenceRange(PatientContextModel):
    low: float | None = None
    high: float | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "ReferenceRange":
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("reference range low cannot exceed high")
        return self


class TemporalAnchor(PatientContextModel):
    observed_at: datetime | None = None
    recorded_at: datetime | None = None
    encounter_id: str | None = None
    relation_to_encounter: TemporalRelation = TemporalRelation.UNKNOWN
    sequence_index: int | None = Field(default=None, ge=0)

    @field_validator("observed_at", "recorded_at")
    @classmethod
    def normalize_temporal_value(cls, value: datetime | None) -> datetime | None:
        return ensure_aware_datetime(value)


class ModalityRecord(PatientContextModel):
    modality: ModalityType
    temporal: TemporalAnchor = Field(default_factory=TemporalAnchor)
    provenance: SourceProvenance | None = None
    missing: list[MissingValueMarker] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Demographics(ModalityRecord):
    modality: ModalityType = ModalityType.DEMOGRAPHICS
    age_years: int | None = Field(default=None, ge=0, le=130)
    sex_at_birth: str | None = None
    gender_identity: str | None = None
    ethnicity: str | None = None
    preferred_language: str | None = None


class VitalSign(ModalityRecord):
    modality: ModalityType = ModalityType.VITALS
    name: str
    value: NormalizedQuantity | None = None
    body_site: str | None = None
    method: str | None = None


class LabValue(ModalityRecord):
    modality: ModalityType = ModalityType.LABS
    test_name: str
    loinc_code: str | None = None
    value: NormalizedQuantity | None = None
    reference_range: ReferenceRange | None = None
    interpretation: str | None = Field(
        default=None,
        description="Normalized interpretation such as low, normal, high, critical, or unknown.",
    )
    specimen: str | None = None


class MedicationStatement(ModalityRecord):
    modality: ModalityType = ModalityType.MEDICATIONS
    medication_name: str
    dose: NormalizedQuantity | None = None
    route: str | None = None
    frequency: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    active: bool | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_medication_time(cls, value: datetime | None) -> datetime | None:
        return ensure_aware_datetime(value)

    @model_validator(mode="after")
    def validate_medication_interval(self) -> "MedicationStatement":
        if self.start_at is not None and self.end_at is not None and self.start_at > self.end_at:
            raise ValueError("medication start_at cannot be after end_at")
        return self


class ClinicalNote(ModalityRecord):
    modality: ModalityType = ModalityType.CLINICAL_NOTES
    note_type: str
    text: str | None = Field(default=None, max_length=100_000)
    author_role: str | None = None
    sections: dict[str, str] = Field(default_factory=dict)


class ImagingMetadata(ModalityRecord):
    modality: ModalityType = ModalityType.IMAGING_METADATA
    study_uid: str | None = None
    modality_code: str
    body_part: str | None = None
    study_description: str | None = None
    report_text: str | None = Field(default=None, max_length=100_000)
    image_count: int | None = Field(default=None, ge=0)


class RawPatientContext(PatientContextModel):
    patient_id: str
    context_id: str | None = None
    demographics: Demographics | None = None
    vitals: list[VitalSign] = Field(default_factory=list)
    labs: list[LabValue] = Field(default_factory=list)
    medications: list[MedicationStatement] = Field(default_factory=list)
    clinical_notes: list[ClinicalNote] = Field(default_factory=list)
    imaging_metadata: list[ImagingMetadata] = Field(default_factory=list)
    global_missing: list[MissingValueMarker] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(PatientContextModel):
    event_id: str
    patient_id: str
    modality: ModalityType
    label: str
    occurred_at: datetime | None = None
    sequence_index: int
    source_record_id: str | None = None
    payload_ref: str

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        return ensure_aware_datetime(value)


class ModalityContext(PatientContextModel):
    modality: ModalityType
    present: bool
    record_count: int = Field(ge=0)
    missing_fields: list[MissingValueMarker] = Field(default_factory=list)
    quality_findings: list[ValidationFinding] = Field(default_factory=list)
    normalized_records: list[dict[str, Any]] = Field(default_factory=list)


class UnifiedPatientRepresentation(PatientContextModel):
    patient_id: str
    context_id: str
    demographics: Demographics | None
    modality_contexts: dict[ModalityType, ModalityContext]
    timeline: list[TimelineEvent]
    retrieval_profile: dict[str, Any] = Field(default_factory=dict)
    explainability_profile: dict[str, Any] = Field(default_factory=dict)
    safety_profile: dict[str, Any] = Field(default_factory=dict)


class StructuredPatientContext(PatientContextModel):
    patient_id: str
    context_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    normalized: RawPatientContext
    unified: UnifiedPatientRepresentation
    validation_findings: list[ValidationFinding] = Field(default_factory=list)


def ensure_aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
