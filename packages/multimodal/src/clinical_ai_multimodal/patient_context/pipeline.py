from collections.abc import Sequence
from uuid import uuid4

from clinical_ai_multimodal.patient_context.schemas import (
    ModalityContext,
    ModalityRecord,
    ModalityType,
    RawPatientContext,
    StructuredPatientContext,
    UnifiedPatientRepresentation,
    ValidationFinding,
    ValidationSeverity,
)
from clinical_ai_multimodal.patient_context.temporal import build_timeline
from clinical_ai_multimodal.patient_context.validation import validate_patient_context


class PatientContextProcessor:
    """Prepare patient context for clinical AI reliability workflows.

    This class intentionally does not infer diagnoses. It normalizes structure, records missingness,
    creates temporal order, and emits validation signals that downstream agents can use for
    evidence-grounded reasoning, safety checks, and explainability.
    """

    def process(self, context: RawPatientContext) -> StructuredPatientContext:
        context_id = context.context_id or f"ctx-{uuid4()}"
        normalized_context = context.model_copy(update={"context_id": context_id}, deep=True)
        findings = validate_patient_context(normalized_context)
        all_records = collect_records(normalized_context)
        timeline = build_timeline(normalized_context.patient_id, all_records)
        modality_contexts = build_modality_contexts(normalized_context, findings)
        unified = UnifiedPatientRepresentation(
            patient_id=normalized_context.patient_id,
            context_id=context_id,
            demographics=normalized_context.demographics,
            modality_contexts=modality_contexts,
            timeline=timeline,
            retrieval_profile=build_retrieval_profile(normalized_context),
            explainability_profile=build_explainability_profile(normalized_context),
            safety_profile=build_safety_profile(normalized_context, findings),
        )
        return StructuredPatientContext(
            patient_id=normalized_context.patient_id,
            context_id=context_id,
            normalized=normalized_context,
            unified=unified,
            validation_findings=findings,
        )


def collect_records(context: RawPatientContext) -> list[ModalityRecord]:
    records: list[ModalityRecord] = []
    if context.demographics is not None:
        records.append(context.demographics)
    records.extend(context.vitals)
    records.extend(context.labs)
    records.extend(context.medications)
    records.extend(context.clinical_notes)
    records.extend(context.imaging_metadata)
    return records


def build_modality_contexts(
    context: RawPatientContext,
    findings: list[ValidationFinding],
) -> dict[ModalityType, ModalityContext]:
    grouped_findings = {
        modality: [finding for finding in findings if finding.modality == modality]
        for modality in ModalityType
    }
    records_by_modality: dict[ModalityType, Sequence[ModalityRecord]] = {
        ModalityType.DEMOGRAPHICS: [context.demographics] if context.demographics else [],
        ModalityType.VITALS: context.vitals,
        ModalityType.LABS: context.labs,
        ModalityType.MEDICATIONS: context.medications,
        ModalityType.CLINICAL_NOTES: context.clinical_notes,
        ModalityType.IMAGING_METADATA: context.imaging_metadata,
    }
    return {
        modality: ModalityContext(
            modality=modality,
            present=bool(records),
            record_count=len(records),
            missing_fields=[
                marker
                for record in records
                for marker in record.missing
            ],
            quality_findings=grouped_findings[modality],
            normalized_records=[record.model_dump(mode="json") for record in records],
        )
        for modality, records in records_by_modality.items()
    }


def build_retrieval_profile(context: RawPatientContext) -> dict[str, object]:
    return {
        "patient_id": context.patient_id,
        "query_terms": sorted(
            {
                *(lab.test_name for lab in context.labs),
                *(vital.name for vital in context.vitals),
                *(medication.medication_name for medication in context.medications),
                *(image.modality_code for image in context.imaging_metadata),
            }
        ),
        "note_types": sorted({note.note_type for note in context.clinical_notes}),
    }


def build_explainability_profile(context: RawPatientContext) -> dict[str, object]:
    return {
        "available_modalities": [
            modality.value
            for modality, present in {
                ModalityType.DEMOGRAPHICS: context.demographics is not None,
                ModalityType.VITALS: bool(context.vitals),
                ModalityType.LABS: bool(context.labs),
                ModalityType.MEDICATIONS: bool(context.medications),
                ModalityType.CLINICAL_NOTES: bool(context.clinical_notes),
                ModalityType.IMAGING_METADATA: bool(context.imaging_metadata),
            }.items()
            if present
        ],
        "source_systems": sorted(
            {
                record.provenance.source_system
                for record in collect_records(context)
                if record.provenance is not None
            }
        ),
    }


def build_safety_profile(
    context: RawPatientContext,
    findings: list[ValidationFinding],
) -> dict[str, object]:
    return {
        "validation_error_count": sum(
            1 for finding in findings if finding.severity == ValidationSeverity.ERROR
        ),
        "validation_warning_count": sum(
            1 for finding in findings if finding.severity == ValidationSeverity.WARNING
        ),
        "missing_field_count": context_global_missing_count(context),
        "requires_human_review": any(
            finding.severity == ValidationSeverity.ERROR for finding in findings
        ),
    }


def context_global_missing_count(context: RawPatientContext) -> int:
    record_missing_count = sum(len(record.missing) for record in collect_records(context))
    return len(context.global_missing) + record_missing_count
