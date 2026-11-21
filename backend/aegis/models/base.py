from typing import Protocol


class ModelProvider(Protocol):
    """Common interface for interchangeable AI providers."""

    def complete(self, prompt: str) -> str:
        """Return a model response for an authorized prompt."""
        ...
