"""Generate synthetic clinical development datasets.

This script creates plausible-but-fictional clinical records for local development,
testing, demos, and pipeline prototyping. It must not be mixed with real patient data.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid5, NAMESPACE_URL


DISCLAIMER = "Synthetic development data only. Not real patient data."

SEXES = ("female", "male", "other", "unknown")
CONDITIONS = (
    "hypertension",
    "type 2 diabetes",
    "asthma",
    "heart failure",
    "chronic kidney disease",
    "community-acquired pneumonia",
    "postoperative monitoring",
)
MEDICATIONS = (
    ("metformin", "500 mg", "oral", "twice daily"),
    ("lisinopril", "10 mg", "oral", "daily"),
    ("atorvastatin", "20 mg", "oral", "nightly"),
    ("albuterol inhaler", "90 mcg", "inhaled", "as needed"),
    ("furosemide", "20 mg", "oral", "daily"),
    ("acetaminophen", "650 mg", "oral", "every 6 hours as needed"),
    ("ceftriaxone", "1 g", "intravenous", "daily"),
)
NOTE_TEMPLATES = (
    "Patient reports {symptom}. Exam notable for {finding}. Plan is to {plan}.",
    "Follow-up assessment for {condition}. Vitals reviewed; {finding}. Continue {plan}.",
    "Synthetic note: {condition} monitoring. Patient denies acute distress. {plan}.",
)
SYMPTOMS = ("mild shortness of breath", "fatigue", "intermittent cough", "reduced appetite")
FINDINGS = (
    "no focal neurologic deficit",
    "lungs clear to auscultation",
    "mild bilateral ankle edema",
    "oxygen saturation stable on room air",
    "blood pressure remains above goal",
)
PLANS = (
    "trend labs and reassess",
    "continue current medications",
    "encourage oral hydration",
    "monitor respiratory status",
    "schedule outpatient follow-up",
)


@dataclass(frozen=True)
class Demographics:
    patient_id: str
    synthetic_mrn: str
    age_years: int
    sex: str
    race_ethnicity: str
    postal_region: str


@dataclass(frozen=True)
class VitalSign:
    patient_id: str
    recorded_at: str
    heart_rate_bpm: int
    spo2_percent: int
    systolic_bp_mm_hg: int
    diastolic_bp_mm_hg: int
    temperature_c: float
    respiratory_rate_bpm: int


@dataclass(frozen=True)
class LabResult:
    patient_id: str
    collected_at: str
    sodium_mmol_l: int
    potassium_mmol_l: float
    creatinine_mg_dl: float
    glucose_mg_dl: int
    hemoglobin_g_dl: float
    wbc_10e3_ul: float
    platelet_10e3_ul: int


@dataclass(frozen=True)
class MedicationOrder:
    patient_id: str
    ordered_at: str
    medication: str
    dose: str
    route: str
    frequency: str
    status: str


@dataclass(frozen=True)
class ClinicalNote:
    patient_id: str
    authored_at: str
    note_type: str
    condition: str
    text: str


@dataclass(frozen=True)
class SyntheticPatientRecord:
    demographics: Demographics
    vitals: list[VitalSign]
    labs: list[LabResult]
    medications: list[MedicationOrder]
    notes: list[ClinicalNote]
    modalities: list[str]


def generate_dataset(
    *,
    patient_count: int,
    seed: int,
    observations_per_patient: int,
    start_at: datetime,
) -> list[SyntheticPatientRecord]:
    validate_generation_args(patient_count, observations_per_patient)
    rng = random.Random(seed)
    records: list[SyntheticPatientRecord] = []

    for index in range(patient_count):
        patient_id = synthetic_id("patient", seed, index)
        age = rng.randint(18, 92)
        condition = rng.choice(CONDITIONS)
        demographics = Demographics(
            patient_id=patient_id,
            synthetic_mrn=f"SYN-{seed:04d}-{index + 1:05d}",
            age_years=age,
            sex=rng.choice(SEXES),
            race_ethnicity=rng.choice(
                ("synthetic-category-a", "synthetic-category-b", "synthetic-category-c")
            ),
            postal_region=f"SYN-{rng.randint(100, 999)}",
        )
        risk_shift = condition_risk_shift(condition)
        vitals = [
            generate_vitals(
                rng=rng,
                patient_id=patient_id,
                recorded_at=start_at + timedelta(hours=8 * offset),
                risk_shift=risk_shift,
            )
            for offset in range(observations_per_patient)
        ]
        labs = [
            generate_labs(
                rng=rng,
                patient_id=patient_id,
                collected_at=start_at + timedelta(hours=12 * offset),
                age=age,
                condition=condition,
            )
            for offset in range(max(1, observations_per_patient // 2))
        ]
        medications = generate_medications(
            rng=rng,
            patient_id=patient_id,
            ordered_at=start_at,
            condition=condition,
        )
        notes = [
            generate_note(
                rng=rng,
                patient_id=patient_id,
                authored_at=start_at + timedelta(hours=12 * offset + 2),
                condition=condition,
            )
            for offset in range(max(1, observations_per_patient // 2))
        ]
        record = SyntheticPatientRecord(
            demographics=demographics,
            vitals=vitals,
            labs=labs,
            medications=medications,
            notes=notes,
            modalities=["tabular", "time_series", "text"],
        )
        validate_record(record)
        records.append(record)

    return records


def generate_vitals(
    *,
    rng: random.Random,
    patient_id: str,
    recorded_at: datetime,
    risk_shift: int,
) -> VitalSign:
    systolic = clamp_int(round(rng.gauss(124 + risk_shift, 14)), 88, 190)
    diastolic = clamp_int(round(rng.gauss(76 + risk_shift / 3, 9)), 48, 118)
    return VitalSign(
        patient_id=patient_id,
        recorded_at=iso(recorded_at),
        heart_rate_bpm=clamp_int(round(rng.gauss(78 + risk_shift / 2, 12)), 45, 145),
        spo2_percent=clamp_int(round(rng.gauss(97 - risk_shift / 10, 2)), 86, 100),
        systolic_bp_mm_hg=systolic,
        diastolic_bp_mm_hg=min(diastolic, systolic - 20),
        temperature_c=round(clamp_float(rng.gauss(36.9 + risk_shift / 35, 0.45), 35.5, 39.8), 1),
        respiratory_rate_bpm=clamp_int(round(rng.gauss(16 + risk_shift / 6, 3)), 10, 32),
    )


def generate_labs(
    *,
    rng: random.Random,
    patient_id: str,
    collected_at: datetime,
    age: int,
    condition: str,
) -> LabResult:
    renal_shift = 0.25 if age > 70 or condition == "chronic kidney disease" else 0
    glucose_shift = 35 if condition == "type 2 diabetes" else 0
    infection_shift = 4 if condition == "community-acquired pneumonia" else 0
    return LabResult(
        patient_id=patient_id,
        collected_at=iso(collected_at),
        sodium_mmol_l=clamp_int(round(rng.gauss(139, 3)), 128, 148),
        potassium_mmol_l=round(clamp_float(rng.gauss(4.1, 0.35), 3.0, 5.8), 1),
        creatinine_mg_dl=round(clamp_float(rng.gauss(0.95 + renal_shift, 0.22), 0.45, 3.2), 2),
        glucose_mg_dl=clamp_int(round(rng.gauss(105 + glucose_shift, 24)), 65, 320),
        hemoglobin_g_dl=round(clamp_float(rng.gauss(13.4, 1.3), 8.5, 17.8), 1),
        wbc_10e3_ul=round(clamp_float(rng.gauss(7.4 + infection_shift, 2.2), 2.5, 22.0), 1),
        platelet_10e3_ul=clamp_int(round(rng.gauss(245, 58)), 80, 620),
    )


def generate_medications(
    *,
    rng: random.Random,
    patient_id: str,
    ordered_at: datetime,
    condition: str,
) -> list[MedicationOrder]:
    count = rng.randint(1, 4)
    selected = list(rng.sample(MEDICATIONS, count))
    if condition == "community-acquired pneumonia":
        selected.append(("ceftriaxone", "1 g", "intravenous", "daily"))
    orders = []
    for offset, medication in enumerate(dict.fromkeys(selected)):
        name, dose, route, frequency = medication
        orders.append(
            MedicationOrder(
                patient_id=patient_id,
                ordered_at=iso(ordered_at + timedelta(hours=offset)),
                medication=name,
                dose=dose,
                route=route,
                frequency=frequency,
                status=rng.choice(("active", "active", "completed")),
            )
        )
    return orders


def generate_note(
    *,
    rng: random.Random,
    patient_id: str,
    authored_at: datetime,
    condition: str,
) -> ClinicalNote:
    template = rng.choice(NOTE_TEMPLATES)
    return ClinicalNote(
        patient_id=patient_id,
        authored_at=iso(authored_at),
        note_type=rng.choice(("progress", "triage", "follow_up", "safety_review")),
        condition=condition,
        text=template.format(
            condition=condition,
            symptom=rng.choice(SYMPTOMS),
            finding=rng.choice(FINDINGS),
            plan=rng.choice(PLANS),
        ),
    )


def export_dataset(
    records: list[SyntheticPatientRecord],
    output_dir: Path,
    *,
    seed: int,
    observations_per_patient: int,
    start_at: datetime,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "disclaimer": DISCLAIMER,
        "schema_version": "synthetic-clinical-dev-v1",
        "generation": {
            "seed": seed,
            "observations_per_patient": observations_per_patient,
            "start_at": iso(start_at),
        },
        "patient_count": len(records),
        "records": [record_to_dict(record) for record in records],
    }
    (output_dir / "dataset.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_csv(output_dir / "patients.csv", [asdict(record.demographics) for record in records])
    write_csv(output_dir / "vitals.csv", flatten(records, "vitals"))
    write_csv(output_dir / "labs.csv", flatten(records, "labs"))
    write_csv(output_dir / "medications.csv", flatten(records, "medications"))
    write_csv(output_dir / "notes.csv", flatten(records, "notes"))
    write_schema(output_dir / "schema.json")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_schema(path: Path) -> None:
    schema = {
        "disclaimer": DISCLAIMER,
        "schema_version": "synthetic-clinical-dev-v1",
        "entities": {
            "Demographics": list(Demographics.__dataclass_fields__),
            "VitalSign": list(VitalSign.__dataclass_fields__),
            "LabResult": list(LabResult.__dataclass_fields__),
            "MedicationOrder": list(MedicationOrder.__dataclass_fields__),
            "ClinicalNote": list(ClinicalNote.__dataclass_fields__),
        },
        "modalities": ["tabular", "time_series", "text"],
        "future_modalities": ["waveform", "image", "pdf", "audio", "device_stream"],
    }
    path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


def flatten(records: list[SyntheticPatientRecord], field_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.extend(asdict(row) for row in getattr(record, field_name))
    return rows


def record_to_dict(record: SyntheticPatientRecord) -> dict[str, Any]:
    return asdict(record)


def validate_generation_args(patient_count: int, observations_per_patient: int) -> None:
    if patient_count < 1:
        raise ValueError("patient_count must be at least 1")
    if patient_count > 100_000:
        raise ValueError("patient_count is too large for this development generator")
    if observations_per_patient < 1:
        raise ValueError("observations_per_patient must be at least 1")


def validate_record(record: SyntheticPatientRecord) -> None:
    demographics = record.demographics
    if not 0 < demographics.age_years < 120:
        raise ValueError(f"Invalid age for {demographics.patient_id}")
    for vital in record.vitals:
        if not 35 <= vital.heart_rate_bpm <= 180:
            raise ValueError(f"Invalid heart rate for {vital.patient_id}")
        if not 70 <= vital.spo2_percent <= 100:
            raise ValueError(f"Invalid SPO2 for {vital.patient_id}")
        if vital.diastolic_bp_mm_hg >= vital.systolic_bp_mm_hg:
            raise ValueError(f"Invalid blood pressure for {vital.patient_id}")
        if not 34 <= vital.temperature_c <= 42:
            raise ValueError(f"Invalid temperature for {vital.patient_id}")
    for lab in record.labs:
        if not 110 <= lab.sodium_mmol_l <= 170:
            raise ValueError(f"Invalid sodium for {lab.patient_id}")
        if not 1.5 <= lab.potassium_mmol_l <= 8.5:
            raise ValueError(f"Invalid potassium for {lab.patient_id}")
        if lab.creatinine_mg_dl <= 0:
            raise ValueError(f"Invalid creatinine for {lab.patient_id}")


def synthetic_id(prefix: str, seed: int, index: int) -> str:
    return f"{prefix}-{uuid5(NAMESPACE_URL, f'clinical-ai-synthetic:{seed}:{index}')}"


def condition_risk_shift(condition: str) -> int:
    return {
        "community-acquired pneumonia": 12,
        "heart failure": 8,
        "chronic kidney disease": 5,
        "postoperative monitoring": 4,
        "hypertension": 6,
    }.get(condition, 0)


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic clinical development data.")
    parser.add_argument("--patients", type=int, default=25, help="Number of synthetic patients.")
    parser.add_argument("--seed", type=int, default=20260518, help="Reproducible random seed.")
    parser.add_argument(
        "--observations-per-patient",
        type=int,
        default=4,
        help="Number of vital-sign observations per patient.",
    )
    parser.add_argument(
        "--start-at",
        default="2026-01-01T08:00:00Z",
        help="UTC start timestamp, for example 2026-01-01T08:00:00Z.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/synthetic_clinical_dataset"),
        help="Output directory for JSON, CSV, and schema files.",
    )
    return parser.parse_args()


def parse_start_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def main() -> None:
    args = parse_args()
    start_at = parse_start_at(args.start_at)
    records = generate_dataset(
        patient_count=args.patients,
        seed=args.seed,
        observations_per_patient=args.observations_per_patient,
        start_at=start_at,
    )
    export_dataset(
        records,
        args.output_dir,
        seed=args.seed,
        observations_per_patient=args.observations_per_patient,
        start_at=start_at,
    )
    print(
        json.dumps(
            {
                "status": "generated",
                "disclaimer": DISCLAIMER,
                "patient_count": len(records),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
