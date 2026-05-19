from typing import Any, Protocol, runtime_checkable

from clinical_ai_multimodal.patient_context.schemas import (
    ModalityRecord,
    ModalityType,
    ValidationFinding,
)


@runtime_checkable
class PatientModalityAdapter(Protocol):
    """Adapter boundary for modality-specific ingestion and normalization."""

    modality: ModalityType

    def parse(self, payload: dict[str, Any]) -> list[ModalityRecord]:
        """Convert source payload into normalized patient context records."""

    def validate(self, records: list[ModalityRecord]) -> list[ValidationFinding]:
        """Run modality-specific quality checks beyond schema validation."""


class ModalityAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[ModalityType, PatientModalityAdapter] = {}

    def register(self, adapter: PatientModalityAdapter) -> None:
        self._adapters[adapter.modality] = adapter

    def get(self, modality: ModalityType) -> PatientModalityAdapter | None:
        return self._adapters.get(modality)

    def registered_modalities(self) -> set[ModalityType]:
        return set(self._adapters)
