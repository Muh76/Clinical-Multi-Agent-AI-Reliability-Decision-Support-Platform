from typing import Protocol


class ModalityNormalizer(Protocol):
    async def normalize(self, payload: bytes, media_type: str) -> dict[str, object]:
        """Normalize modality-specific input into a platform representation."""

