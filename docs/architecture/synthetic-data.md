# Synthetic Clinical Dataset Generator

## Purpose

The synthetic dataset generator creates fictional clinical-looking data for local development, API demos, pipeline prototyping, reliability evaluation fixtures, and observability testing.

This is not real patient data and must not be treated as clinical evidence.

## Generated Entities

The generator produces:

- demographics;
- vital signs;
- lab results;
- medication orders;
- short clinical notes;
- timestamps;
- modality metadata.

Current modalities:

- `tabular`;
- `time_series`;
- `text`.

Future modalities can extend the same patient/case IDs with waveform, image, PDF, audio, and device-stream artifacts.

## Usage

```bash
python scripts/generate_synthetic_clinical_dataset.py \
  --patients 25 \
  --observations-per-patient 4 \
  --seed 20260518 \
  --output-dir tmp/synthetic_clinical_dataset
```

## Outputs

```text
dataset.json
patients.csv
vitals.csv
labs.csv
medications.csv
notes.csv
schema.json
```

## Reproducibility

Generation is deterministic for the same seed, patient count, observation count, and start timestamp. Synthetic patient IDs are UUIDv5 values derived from the seed and row index.

## Validation

The generator validates:

- patient counts and observation counts;
- plausible age ranges;
- vital-sign ranges;
- blood pressure consistency;
- basic lab ranges.

The ranges are medically plausible for development fixtures, but they are not validated for diagnosis, treatment, or clinical research.

## Limitations

- The generator does not represent real disease progression.
- The notes are templated and intentionally short.
- Demographic labels are synthetic categories, not real-world population modeling.
- Medication choices are plausible examples, not treatment recommendations.
- Correlations between conditions, vitals, labs, and medications are simplified.

## Expansion Strategy

Future multimodal support should add sidecar manifests rather than overloading CSV rows:

- waveform files linked by `patient_id` and `recorded_at`;
- synthetic radiology-like image metadata or generated image fixtures;
- PDF note bundles for document ingestion testing;
- audio transcript fixtures;
- device-stream chunks for time-series ingestion.

Keep generated artifacts clearly labeled as synthetic and never combine them with real patient records in the same storage location.
