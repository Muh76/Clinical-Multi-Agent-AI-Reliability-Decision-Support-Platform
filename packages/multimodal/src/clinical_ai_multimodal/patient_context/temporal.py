from collections.abc import Iterable
from datetime import UTC, datetime

from clinical_ai_multimodal.patient_context.schemas import (
    ModalityRecord,
    ModalityType,
    TimelineEvent,
)


def build_timeline(patient_id: str, records: Iterable[ModalityRecord]) -> list[TimelineEvent]:
    unsorted_events = [
        TimelineEvent(
            event_id=f"{record.modality.value}:{index}",
            patient_id=patient_id,
            modality=record.modality,
            label=event_label(record),
            occurred_at=event_time(record),
            sequence_index=index,
            source_record_id=record.provenance.source_record_id if record.provenance else None,
            payload_ref=f"{record.modality.value}[{index}]",
        )
        for index, record in enumerate(records)
    ]
    sorted_events = sorted(
        unsorted_events,
        key=lambda event: (
            event.occurred_at is None,
            event.occurred_at or datetime.max.replace(tzinfo=UTC),
            event.sequence_index,
        ),
    )
    return [
        event.model_copy(update={"sequence_index": sequence_index})
        for sequence_index, event in enumerate(sorted_events)
    ]


def event_time(record: ModalityRecord) -> datetime | None:
    return record.temporal.observed_at or record.temporal.recorded_at


def event_label(record: ModalityRecord) -> str:
    modality = record.modality
    if modality == ModalityType.VITALS and hasattr(record, "name"):
        return str(record.name)
    if modality == ModalityType.LABS and hasattr(record, "test_name"):
        return str(record.test_name)
    if modality == ModalityType.MEDICATIONS and hasattr(record, "medication_name"):
        return str(record.medication_name)
    if modality == ModalityType.CLINICAL_NOTES and hasattr(record, "note_type"):
        return str(record.note_type)
    if modality == ModalityType.IMAGING_METADATA and hasattr(record, "modality_code"):
        return str(record.modality_code)
    return modality.value
