from __future__ import annotations

from abc import ABC, abstractmethod
from math import ceil


class InferenceUnavailable(RuntimeError):
    pass


class InferenceEngine(ABC):
    """Text conversation in, text response out."""

    context_length = 8192
    max_response_tokens = 512

    @abstractmethod
    def respond(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

    def count_message_tokens(self, messages: list[dict[str, str]]) -> int:
        """Count a formatted prompt; remote engines use a conservative fallback."""
        characters = sum(len(str(message.get("content", ""))) for message in messages)
        formatting_allowance = 4 * len(messages) + 3
        return max(1, ceil(characters / 4) + formatting_allowance)
