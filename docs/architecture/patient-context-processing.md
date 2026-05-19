# Patient Context Processing Layer

The Patient Context Processing Layer prepares multimodal patient context for reliability,
evidence-grounding, explainability, safety evaluation, and downstream orchestration. It is not a
diagnosis or recommendation engine. Its job is to make clinical inputs explicit, normalized,
auditable, temporally ordered, and safe for later agents to consume.

## Architecture Design

The layer lives in `packages/multimodal/src/clinical_ai_multimodal/patient_context` and is centered
on `PatientContextProcessor`.

1. Source adapters parse modality-specific payloads.
2. Pydantic schemas enforce strict structure and bounds.
3. Normalization utilities standardize timestamps, units, numeric quantities, reference ranges, and
   missing value markers.
4. Validation logic emits quality findings without inventing missing clinical facts.
5. Temporal preparation builds a patient timeline across modalities.
6. Unified representations expose modality contexts plus retrieval, explainability, and safety
   profiles for downstream agents.

The processor intentionally keeps raw normalized records and derived profiles together. This allows
later agents to ground explanations in source records instead of opaque embeddings or model memory.

## Design Decisions

- **Strict schemas over loose dictionaries**: clinical reliability depends on explicit field names,
  allowed modalities, provenance, and validation failures. Pydantic rejects unexpected fields by
  default.
- **Missingness is first-class**: absence can mean not collected, redacted, not applicable, unknown,
  or source failure. The layer records missingness instead of silently converting it to `None`.
- **Normalization is conservative**: utilities normalize common units such as Fahrenheit to Celsius
  and pounds to kilograms, but do not infer values.
- **Validation emits findings, not diagnoses**: implausible values, missing demographics, empty
  modalities, and reference range flags are quality signals for safety and orchestration.
- **Temporal events are modality-neutral**: every record can become a timeline event. This supports
  future temporal reasoning, trend detection, and episode construction.
- **Profiles are downstream contracts**: retrieval terms, explainability source summaries, and safety
  counts give agents structured context without forcing those agents to inspect every raw record.
- **Modality adapters are pluggable**: `PatientModalityAdapter` allows future imaging, waveform,
  genomics, device, or document parsers to attach without changing the processor core.

## Pydantic Schemas

Core schemas are defined in `schemas.py`:

- `RawPatientContext`: patient-level input container.
- `Demographics`, `VitalSign`, `LabValue`, `MedicationStatement`, `ClinicalNote`,
  `ImagingMetadata`: modality records with shared provenance, temporal anchors, tags, and missingness.
- `NormalizedQuantity` and `ReferenceRange`: normalized numeric values.
- `ValidationFinding`: structured quality, safety, and consistency findings.
- `TimelineEvent`: temporal abstraction for cross-modality ordering.
- `ModalityContext`: normalized per-modality view.
- `UnifiedPatientRepresentation`: downstream-ready context for agents, retrieval, explainability,
  safety, and orchestration.
- `StructuredPatientContext`: final processor output.

## Processing Pipeline Structure

`PatientContextProcessor.process()` performs these steps:

1. Assign or preserve a `context_id`.
2. Validate patient-level and modality-level consistency.
3. Collect modality records.
4. Build a cross-modality timeline.
5. Build one `ModalityContext` per modality.
6. Build retrieval, explainability, and safety profiles.
7. Return `StructuredPatientContext`.

## Normalization Utilities

`normalization.py` includes:

- `parse_datetime()`: ISO timestamp parsing with UTC fallback for naive datetimes.
- `canonical_unit()`: local unit alias normalization.
- `coerce_float()`: safe numeric conversion.
- `normalize_quantity()`: numeric and unit normalization.
- `normalize_reference_range()`: reference range preparation.
- `missing_marker()`: explicit missing value marker construction.

These utilities are deliberately small and replaceable. A future production deployment can map them
to UCUM, FHIR Quantity, LOINC, RxNorm, SNOMED CT, and DICOM vocabulary services.

## Validation Logic

`validation.py` checks for:

- absent demographics,
- empty modalities,
- missing vital or lab values,
- implausible normalized vital ranges,
- lab values outside supplied reference ranges.

Findings are designed for orchestration. For example, an error can route the case to human review,
while an info finding can be used in explanations or evidence weighting.

## Temporal Data Preparation

`temporal.py` converts records into `TimelineEvent` objects sorted by observed or recorded time. Each
event retains a payload reference such as `labs[0]`, which lets downstream temporal reasoning connect
an event back to the normalized source record.

Later extensions can add:

- rolling windows,
- trend summaries,
- encounter-relative features,
- event coalescing,
- uncertainty intervals,
- missingness timelines.

## Modality Abstraction Design

`modalities.py` defines `PatientModalityAdapter`:

```python
class PatientModalityAdapter(Protocol):
    modality: ModalityType

    def parse(self, payload: dict[str, Any]) -> list[ModalityRecord]: ...
    def validate(self, records: list[ModalityRecord]) -> list[ValidationFinding]: ...
```

This separates source-specific ingestion from the processor. A FHIR vital-sign adapter, CSV lab
adapter, DICOM metadata adapter, or note-section parser can each normalize records into the same
patient context contract.

## Example Structured Patient Context Object

```python
from clinical_ai_multimodal.patient_context import PatientContextProcessor
from clinical_ai_multimodal.patient_context.schemas import (
    Demographics,
    LabValue,
    NormalizedQuantity,
    RawPatientContext,
    ReferenceRange,
    TemporalAnchor,
    VitalSign,
)

raw_context = RawPatientContext(
    patient_id="patient-001",
    demographics=Demographics(age_years=67, sex_at_birth="female"),
    vitals=[
        VitalSign(
            name="heart_rate",
            value=NormalizedQuantity(value=112, unit="beats/min"),
            temporal=TemporalAnchor(observed_at="2026-05-19T08:10:00Z"),
        )
    ],
    labs=[
        LabValue(
            test_name="creatinine",
            value=NormalizedQuantity(value=1.8, unit="mg/dL"),
            reference_range=ReferenceRange(low=0.6, high=1.2, unit="mg/dL"),
            temporal=TemporalAnchor(observed_at="2026-05-19T08:30:00Z"),
        )
    ],
)

structured = PatientContextProcessor().process(raw_context)
```

The resulting `structured.unified` object contains:

- per-modality normalized records,
- a sorted timeline,
- retrieval query terms such as `creatinine` and `heart_rate`,
- explainability source summaries,
- safety counts and human-review flags.

This output can be passed to retrieval, safety critics, evaluation workflows, and agent
orchestration without asking those components to reinterpret raw clinical payloads.
