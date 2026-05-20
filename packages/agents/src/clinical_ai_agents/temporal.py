from datetime import datetime
from typing import Any

from clinical_ai_multimodal.patient_context.schemas import TimelineEvent


def summarize_timeline(events: list[TimelineEvent]) -> dict[str, Any]:
    ordered_events = sorted(
        events,
        key=lambda event: (
            event.occurred_at is None,
            event.occurred_at or datetime.max,
            event.sequence_index,
        ),
    )
    first_event = next((event for event in ordered_events if event.occurred_at), None)
    last_event = next((event for event in reversed(ordered_events) if event.occurred_at), None)
    events_without_time = sum(1 for event in events if event.occurred_at is None)
    return {
        "event_count": len(events),
        "events_with_time": len(events) - events_without_time,
        "events_without_time": events_without_time,
        "first_event_at": first_event.occurred_at.isoformat() if first_event else None,
        "last_event_at": last_event.occurred_at.isoformat() if last_event else None,
        "modality_event_counts": modality_event_counts(events),
        "temporal_completeness": temporal_completeness(events),
    }


def modality_event_counts(events: list[TimelineEvent]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        modality = event.modality.value
        counts[modality] = counts.get(modality, 0) + 1
    return counts


def temporal_completeness(events: list[TimelineEvent]) -> float:
    if not events:
        return 0.0
    return sum(1 for event in events if event.occurred_at is not None) / len(events)
