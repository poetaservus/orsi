from __future__ import annotations

from abc import ABC, abstractmethod
from math import ceil
from typing import Iterable

from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelProtocolFailureCode,
    ModelResponse,
)


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

    def respond_with_capabilities(
        self,
        messages: list[dict[str, str]],
        capabilities: Iterable[ModelCapabilityDefinition],
    ) -> ModelResponse:
        del messages, capabilities
        return ModelResponse.failure(
            ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS,
            "This model adapter does not support native capability calls.",
        )
