from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from clinical_ai_multimodal.patient_context.schemas import (
    MissingValueMarker,
    MissingnessReason,
    NormalizedQuantity,
    ReferenceRange,
)


UNIT_ALIASES: dict[str, str] = {
    "bpm": "beats/min",
    "beats per minute": "beats/min",
    "c": "Cel",
    "celsius": "Cel",
    "f": "degF",
    "fahrenheit": "degF",
    "kg": "kg",
    "kilogram": "kg",
    "lbs": "lb",
    "pounds": "lb",
    "mmhg": "mm[Hg]",
    "mg/dl": "mg/dL",
    "mmol/l": "mmol/L",
    "%": "%",
}

MISSING_SENTINELS = {"", "na", "n/a", "none", "null", "unknown", "not recorded", "redacted"}


def parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.strip().replace("Z", "+00:00")
        if not normalized:
            return None
        parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def canonical_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    normalized = unit.strip()
    if not normalized:
        return None
    return UNIT_ALIASES.get(normalized.lower(), normalized)


def coerce_float(value: str | float | int | Decimal | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and is_missing_value(value):
        return None
    try:
        return float(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError):
        return None


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_SENTINELS
    return False


def missing_marker(field_name: str, value: Any) -> MissingValueMarker | None:
    if not is_missing_value(value):
        return None
    reason = (
        MissingnessReason.REDACTED
        if str(value).strip().lower() == "redacted"
        else MissingnessReason.NOT_PROVIDED
    )
    return MissingValueMarker(field_name=field_name, reason=reason)


def normalize_quantity(
    value: str | float | int | Decimal | None,
    unit: str | None,
    *,
    original_unit: str | None = None,
) -> NormalizedQuantity | None:
    numeric_value = coerce_float(value)
    normalized_unit = canonical_unit(unit)
    if numeric_value is None or normalized_unit is None:
        return None

    if normalized_unit == "degF":
        return NormalizedQuantity(
            value=round((numeric_value - 32.0) * 5.0 / 9.0, 3),
            unit="Cel",
            original_value=value,
            original_unit=original_unit or unit,
        )
    if normalized_unit == "lb":
        return NormalizedQuantity(
            value=round(numeric_value * 0.45359237, 3),
            unit="kg",
            original_value=value,
            original_unit=original_unit or unit,
        )
    return NormalizedQuantity(
        value=numeric_value,
        unit=normalized_unit,
        original_value=value,
        original_unit=original_unit or unit,
    )


def normalize_reference_range(
    low: str | float | int | None,
    high: str | float | int | None,
    unit: str | None,
) -> ReferenceRange | None:
    normalized_low = coerce_float(low)
    normalized_high = coerce_float(high)
    normalized_unit = canonical_unit(unit)
    if normalized_low is None and normalized_high is None and normalized_unit is None:
        return None
    return ReferenceRange(low=normalized_low, high=normalized_high, unit=normalized_unit)


def collect_missing(markers: Iterable[MissingValueMarker | None]) -> list[MissingValueMarker]:
    return [marker for marker in markers if marker is not None]
