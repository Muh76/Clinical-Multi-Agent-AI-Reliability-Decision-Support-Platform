from typing import Protocol

from clinical_ai_shared.types import RiskSeverity


class SafetyCritic(Protocol):
    async def assess(self, content: str) -> RiskSeverity:
        """Assess the severity of a candidate recommendation or explanation."""

