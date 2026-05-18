from typing import Protocol


class Agent(Protocol):
    name: str

    async def run(self, input_text: str) -> str:
        """Run an agent workflow and return a structured response payload."""

