from typing import Protocol


class Evaluator(Protocol):
    async def evaluate(self, case_id: str) -> dict[str, float]:
        """Evaluate reliability, faithfulness, and safety metrics for a case."""

