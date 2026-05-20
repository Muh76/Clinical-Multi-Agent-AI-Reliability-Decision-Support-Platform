# MIMIC-IV Processing Architecture

This document defines a clean MIMIC-IV preprocessing architecture for vitals, labs, medications,
notes, timestamps, and admissions. It does not build predictive models. Its purpose is to transform
raw MIMIC-IV tables into structured, auditable patient context that can support retrieval,
explainability, safety analysis, temporal reasoning, and future multimodal orchestration.

MIMIC-IV data must be treated as de-identified research data with source-specific conventions,
shifted dates, sparse modalities, and complex hospital timelines. The processing layer should make
those conventions explicit rather than hiding them behind opaque feature engineering.

## MIMIC Processing Architecture

```text
MIMIC-IV files or warehouse tables
  -> scalable table loaders
  -> schema mapping and terminology normalization
  -> modality processors
  -> encounter/admission resolver
  -> temporal event preparation
  -> missingness and data quality annotation
  -> patient timeline builder
  -> structured patient context generator
  -> retrieval, explainability, safety, and orchestration outputs
```

Recommended modules:

- **MimicDataLoader**: reads large MIMIC-IV CSV, Parquet, or database tables in chunks or partitioned
  scans.
- **MimicSchemaMapper**: maps MIMIC source columns to platform fields and stable record IDs.
- **AdmissionResolver**: builds the patient-admission-stay frame from admissions and timestamps.
- **ModalityProcessor**: source-specific processors for vitals, labs, medications, and notes.
- **TemporalEventBuilder**: converts normalized records into modality-neutral timeline events.
- **MissingnessProfiler**: records absent, delayed, unknown, redacted, not-applicable, and source
  failure states.
- **PatientTimelineBuilder**: creates sorted patient and admission timelines.
- **PatientContextGenerator**: emits the platform's structured patient context contract.
- **ValidationReporter**: emits quality findings, range checks, temporal consistency issues, and
  provenance gaps.

The source-specific MIMIC layer should sit before `PatientContextProcessor`. It adapts MIMIC records
into the existing patient context schemas instead of creating a parallel downstream representation.

## Schema Mapping

The platform should map only the required data domains for this phase.

| Domain | MIMIC-IV source | Key identifiers | Platform output |
| --- | --- | --- | --- |
| Admissions | `hosp.admissions` | `subject_id`, `hadm_id` | admission interval, admission type, discharge/death metadata |
| Vitals | ICU `chartevents` subset or derived vitals table | `subject_id`, `hadm_id`, `stay_id`, `itemid`, `charttime` | `VitalSign` records |
| Labs | `hosp.labevents` + `hosp.d_labitems` | `subject_id`, `hadm_id`, `itemid`, `charttime`, `storetime` | `LabValue` records |
| Medications | `hosp.prescriptions`, ICU medication events when included | `subject_id`, `hadm_id`, medication name, start/stop time | `MedicationStatement` records |
| Notes | MIMIC-IV-Note discharge/radiology/clinical notes when licensed | `subject_id`, `hadm_id`, `note_id`, `charttime`, `storetime` | `ClinicalNote` records |
| Timestamps | all temporal source columns | `charttime`, `storetime`, `starttime`, `stoptime`, `admittime`, `dischtime` | `TemporalAnchor` and timeline events |

Core identifier mapping:

```text
patient_id      <- "mimic-subject-{subject_id}"
admission_id    <- "mimic-hadm-{hadm_id}"
encounter_id    <- hadm_id when present, otherwise stay_id or source-specific fallback
source_record_id <- "{table}:{primary identifiers}"
source_system    <- "mimic-iv"
```

Admission fields:

| Platform field | MIMIC source |
| --- | --- |
| `patient_id` | `subject_id` |
| `admission_id` | `hadm_id` |
| `admitted_at` | `admittime` |
| `discharged_at` | `dischtime` |
| `deceased_at` | `deathtime` |
| `admission_type` | `admission_type` |
| `admission_location` | `admission_location` |
| `discharge_location` | `discharge_location` |
| `insurance` | `insurance`, if retained for analysis governance |
| `language` | `language`, if retained and approved |
| `marital_status` | `marital_status`, if retained and approved |
| `race` | `race`, if retained and approved |

Vitals fields:

| Platform field | MIMIC source |
| --- | --- |
| `name` | normalized label from `d_items` or curated itemid map |
| `value.value` | numeric `valuenum` |
| `value.unit` | normalized `valueuom` |
| `observed_at` | `charttime` |
| `recorded_at` | `storetime` when available |
| `source_record_id` | `chartevents:{stay_id}:{itemid}:{charttime}` |

Labs fields:

| Platform field | MIMIC source |
| --- | --- |
| `test_name` | normalized label from `d_labitems` |
| `value.value` | numeric `valuenum` |
| `value.unit` | normalized `valueuom` |
| `reference_range.low` | `ref_range_lower` |
| `reference_range.high` | `ref_range_upper` |
| `flag` | abnormal flag when available |
| `observed_at` | `charttime` |
| `recorded_at` | `storetime` |
| `source_record_id` | `labevents:{itemid}:{charttime}:{storetime}` |

Medication fields:

| Platform field | MIMIC source |
| --- | --- |
| `medication_name` | `drug`, `drug_name_generic`, or normalized medication label |
| `dose` | dose fields when available |
| `route` | `route` |
| `frequency` | `prod_strength`, `formulary_drug_cd`, or explicit schedule where available |
| `started_at` | `starttime` |
| `ended_at` | `stoptime` |
| `source_record_id` | `prescriptions:{pharmacy_id}` or stable row hash |

Notes fields:

| Platform field | MIMIC source |
| --- | --- |
| `note_type` | note table/category |
| `text` | de-identified note text |
| `observed_at` | `charttime` |
| `recorded_at` | `storetime` |
| `source_record_id` | `notes:{note_id}` |
| `tags` | category, note type, provider/service labels when available |

## Timeline Builder

The timeline builder creates two related timelines:

- **Patient timeline**: all selected events for a `subject_id`, ordered by shifted MIMIC timestamps.
- **Admission timeline**: events scoped to a `hadm_id`, ordered relative to `admittime`.

Timeline event contract:

```json
{
  "event_id": "mimic-hadm-200001:vitals:heart_rate:0",
  "patient_id": "mimic-subject-100001",
  "admission_id": "mimic-hadm-200001",
  "modality": "vitals",
  "event_type": "heart_rate",
  "observed_at": "2160-05-20T08:15:00",
  "recorded_at": "2160-05-20T08:17:00",
  "relative_minutes_from_admission": 135,
  "source_table": "chartevents",
  "source_record_id": "chartevents:300001:220045:2160-05-20T08:15:00",
  "payload_ref": "vitals[12]",
  "quality_flags": []
}
```

Timeline construction steps:

1. Load admissions and build admission intervals.
2. Attach each event to `hadm_id` when present.
3. For records without `hadm_id`, infer admission only when the event timestamp falls inside exactly
   one admission interval; otherwise mark as unresolved.
4. Normalize timestamps while preserving MIMIC's de-identified shifted chronology.
5. Compute relative time from admission and, where relevant, discharge.
6. Sort by `observed_at`, then `recorded_at`, then source priority.
7. Keep duplicate clinical observations if they have different source records, but mark duplicate-like
   clusters for downstream review.
8. Emit timeline quality findings for events outside admission intervals, missing timestamps,
   negative durations, and impossible medication intervals.

The builder must not infer clinical state. It only orders and annotates observed records.

## Patient Context Generator

The patient context generator turns admission-scoped records into a structured patient context object
compatible with retrieval, safety, explainability, temporal reasoning, and orchestration.

Generated context sections:

- `identity`: de-identified patient and admission identifiers.
- `admission`: admission interval and admission/discharge metadata.
- `modalities`: normalized vitals, labs, medications, and notes.
- `timeline`: modality-neutral temporal events.
- `missingness`: explicit modality and field-level missingness profile.
- `retrieval_profile`: clinical terms and source references useful for evidence retrieval.
- `explainability_profile`: source table counts, representative events, provenance summaries.
- `safety_profile`: validation findings, missing critical modalities, abnormal values, unresolved
  temporal anchors.
- `orchestration_profile`: available modalities, time span, event density, and readiness flags for
  future multimodal agents.

Example output shape:

```json
{
  "context_id": "mimic-subject-100001-hadm-200001",
  "patient_id": "mimic-subject-100001",
  "admission_id": "mimic-hadm-200001",
  "source_system": "mimic-iv",
  "modalities_available": ["admissions", "vitals", "labs", "medications", "notes"],
  "timeline_event_count": 642,
  "missing_modalities": [],
  "retrieval_terms": ["heart_rate", "creatinine", "vancomycin", "discharge summary"],
  "human_review_recommended": false
}
```

Retrieval support:

- expose normalized clinical terms from vitals, labs, medication names, note headings, and admission
  metadata;
- preserve source record IDs so retrieved explanations can cite patient-context records;
- create note chunks with timestamps and note type metadata for patient-record retrieval.

Explainability support:

- retain raw source provenance for every normalized record;
- include value, unit, timestamp, source table, and mapping confidence;
- report why a modality is absent rather than silently omitting it.

Safety support:

- flag implausible values, missing high-value modalities, conflicting units, and unresolved event
  ordering;
- keep validation findings separate from clinical conclusions.

## Modality Processors

Each modality processor should implement the same high-level interface:

```text
load source rows
  -> map source identifiers
  -> normalize labels and units
  -> validate values and timestamps
  -> attach provenance
  -> emit normalized records + findings
```

### Admissions Processor

Responsibilities:

- load `subject_id`, `hadm_id`, admission and discharge timestamps;
- normalize admission metadata;
- define admission intervals;
- detect overlapping admissions per patient;
- mark missing `dischtime`, `deathtime`, or inconsistent intervals;
- provide the temporal frame for admission-relative reasoning.

### Vitals Processor

Responsibilities:

- select only curated vital-sign `itemid` values;
- normalize labels such as heart rate, respiratory rate, temperature, oxygen saturation, systolic
  blood pressure, diastolic blood pressure, mean arterial pressure, and weight when included;
- normalize units conservatively;
- reject or flag nonnumeric values when numeric values are required;
- preserve repeated measurements and device/charting provenance;
- emit implausible-range findings without diagnosing the patient.

### Labs Processor

Responsibilities:

- join `labevents` to `d_labitems`;
- normalize common lab names, units, reference ranges, and abnormal flags;
- preserve specimen and fluid metadata when available;
- distinguish observed time from stored time;
- retain values that are textual or censored as missing or qualitative values rather than forcing a
  numeric conversion;
- flag unit conflicts for the same test within an admission.

### Medications Processor

Responsibilities:

- normalize medication names from prescriptions or medication event tables;
- preserve route, dose, start time, stop time, and frequency fields when available;
- identify active medication intervals;
- flag missing start or stop times, negative intervals, duplicate overlapping orders, and unclear
  dose units;
- avoid mapping medications to treatment intent unless explicitly provided by source text.

### Notes Processor

Responsibilities:

- load allowed MIMIC-IV-Note records by `subject_id` and `hadm_id`;
- preserve note type, category, chart time, store time, and note ID;
- chunk long notes by section when section headings are available;
- retain de-identification placeholders as source text artifacts;
- produce retrieval-ready note snippets with source IDs and timestamps;
- flag empty, extremely short, duplicate, or timestamp-missing notes.

## Temporal Abstractions

Temporal abstractions should make event timing usable without turning preprocessing into modeling.

Recommended abstractions:

- **Absolute shifted time**: original MIMIC shifted timestamp for ordering within a patient.
- **Admission-relative time**: minutes or hours from `admittime`.
- **Discharge-relative time**: minutes or hours before `dischtime` when useful for note alignment.
- **Event interval**: start and stop time for medication exposure or admission duration.
- **Observation event**: point-in-time vitals, labs, and note chart times.
- **Record latency**: difference between observed/chart time and stored time.
- **Temporal window**: configurable grouping such as first 6 hours, first 24 hours, daily, or full
  admission, used only for summaries and orchestration readiness.
- **Uncertain timestamp**: explicit state when only partial, missing, or source-dependent time exists.

Temporal event types:

| Event type | Examples |
| --- | --- |
| `admission_started` | hospital admission time |
| `admission_ended` | discharge time |
| `vital_observed` | heart rate, blood pressure, oxygen saturation |
| `lab_resulted` | creatinine, hemoglobin, lactate |
| `medication_started` | antibiotic or other medication start |
| `medication_stopped` | medication stop |
| `note_recorded` | discharge summary or clinical note |

## Preprocessing Workflow

1. Register a MIMIC dataset snapshot with version, table paths, license boundary, and processing
   configuration.
2. Load admissions first and create patient/admission partitions.
3. Load vitals, labs, medications, and notes in scalable chunks filtered to selected `subject_id` or
   `hadm_id` partitions.
4. Join dictionary tables such as `d_items` and `d_labitems` for labels and units.
5. Apply schema mapping and terminology normalization.
6. Normalize timestamps and attach admission-relative time.
7. Run modality-specific validation.
8. Build missingness profiles per admission.
9. Build patient and admission timelines.
10. Generate structured patient context outputs.
11. Write outputs as partitioned JSONL or Parquet by `subject_id` and `hadm_id`.
12. Emit observability metrics and validation reports.
13. Run sample audits against raw source rows before promoting the processed snapshot.

Scalability recommendations:

- use chunked CSV readers, Polars lazy scans, DuckDB, Spark, or warehouse SQL depending on dataset
  size and deployment environment;
- partition intermediate outputs by `subject_id` or `hadm_id`;
- avoid loading all `chartevents` or notes into memory;
- keep dictionary joins broadcast-sized and cached;
- write deterministic record IDs so reruns update the same records;
- separate raw, normalized, and context outputs.

## Missing Data Handling

Missingness should be represented explicitly because absent clinical data can affect safety,
explainability, and orchestration.

Missingness categories:

- `not_collected`: modality or field absent in source records;
- `not_applicable`: field does not apply to this record type;
- `unknown`: source value missing without explanation;
- `redacted`: de-identification or privacy removal;
- `unresolved_mapping`: source item exists but no approved mapping exists;
- `invalid_value`: value present but fails parsing or validation;
- `outside_scope`: modality exists in MIMIC but is excluded from this processing phase;
- `source_failure`: loader or join failure prevented processing.

Handling rules:

- do not impute values in the preprocessing layer;
- do not replace missing clinical measurements with normal values;
- propagate missingness into validation findings and safety profiles;
- distinguish missing modality from empty admission window;
- count missing critical timestamps separately from missing values;
- preserve raw source value when it is safe and useful for audit.

Example missingness profile:

```json
{
  "admission_id": "mimic-hadm-200001",
  "modalities": {
    "vitals": {"status": "present", "record_count": 218},
    "labs": {"status": "present", "record_count": 93},
    "medications": {"status": "present", "record_count": 41},
    "notes": {"status": "not_collected", "record_count": 0}
  },
  "field_findings": [
    {
      "field": "labs.storetime",
      "missing_count": 7,
      "missingness_type": "unknown"
    }
  ]
}
```

## Validation Strategies

Validation should detect source, mapping, temporal, and clinical-plausibility issues without creating
diagnoses or labels.

Schema validation:

- required identifiers exist for each table;
- timestamp columns parse consistently;
- numeric columns parse when numeric values are expected;
- dictionary joins resolve expected labels;
- output records conform to patient context schemas.

Temporal validation:

- admission `admittime` occurs before `dischtime`;
- event timestamps fall inside or near the admission window unless explicitly allowed;
- medication start time is before stop time;
- store time is not implausibly earlier than chart time;
- patient timeline ordering is stable across reruns.

Clinical plausibility validation:

- vital values fall within broad human-plausible ranges;
- lab values are not silently converted across incompatible units;
- reference range flags match supplied reference bounds when numeric;
- medication dose fields are preserved but not interpreted when ambiguous.

Provenance validation:

- every normalized record has source table, source record ID, patient ID, and timestamp status;
- every note chunk links back to note ID and admission when available;
- every timeline event has a payload reference;
- every missingness finding identifies modality and field.

Regression validation:

- row counts by table, patient, and admission match expected snapshot ranges;
- processed output is deterministic for the same input snapshot;
- known fixture admissions produce stable timelines;
- sampled records can be traced back to raw MIMIC rows;
- no predictive labels or target variables are generated by this preprocessing pipeline.

## MIMIC Complexities

MIMIC-IV is powerful but not simple. It contains hospital and ICU data with different table grains,
dictionary mappings, timestamp conventions, missing fields, and source-system artifacts. A single
clinical concept can appear under multiple item IDs, units, or labels. Some events are charted after
they occur. Some records are linked to admissions, some to ICU stays, and some require careful
interval logic.

The architecture should therefore favor explicit source mappings, deterministic identifiers, visible
missingness, and conservative normalization. The output should help downstream agents reason over the
patient timeline, not hide uncertainty behind feature vectors.

## Temporal Healthcare Challenges

Healthcare timelines are not simple event streams. Observation time, chart time, store time,
medication start/stop time, admission time, discharge time, and note time can all mean different
things. Late charting, repeated measurements, transfers, overlapping medication orders, and shifted
de-identified dates create ambiguity.

Best practice is to preserve multiple timestamps, name their meaning, and derive admission-relative
time as an additional field rather than overwriting source time. Temporal reasoning components can
then decide which timestamp is appropriate for their task.

## Healthcare Preprocessing Best Practices

- Keep preprocessing separate from prediction.
- Preserve provenance for every normalized value.
- Normalize labels and units conservatively.
- Make missingness explicit and queryable.
- Avoid imputation, diagnosis inference, or outcome labeling in this layer.
- Keep source snapshots versioned and reproducible.
- Use modality-specific validation plus cross-modality temporal checks.
- Store outputs in partitioned, replayable formats.
- Maintain audit links from patient context back to raw source rows.
- Treat notes as clinical text with timestamps and provenance, not as unbounded prompt material.

This architecture prepares MIMIC-IV data as reliable context for retrieval, explainability, safety,
temporal reasoning, and future multimodal orchestration while keeping clinical modeling decisions out
of the preprocessing layer.
