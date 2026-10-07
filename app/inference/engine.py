from __future__ import annotations

from abc import ABC, abstractmethod
from math import ceil
from typing import Iterable
from app.inference.attachments import AttachmentError, has_attachments

from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelProtocolFailureCode,
    ModelResponse,
)


class InferenceUnavailable(RuntimeError):
    pass


class InferenceEngine(ABC):
    """Conversation adapter. Attachment support requires explicit provider implementation."""

    context_length = 8192
    max_response_tokens = 512
    supports_attachment_inputs = False

    def respond_with_attachments(self, messages, *, attachment_store):
        raise AttachmentError("Image and file input is not enabled for this model yet.")

    def count_attachment_message_tokens(self, messages):
        raise AttachmentError("This model cannot account for image and file input yet.")

    def set_activity_observer(self, observer=None):
        self._activity_observer = observer

    @abstractmethod
    def respond(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

    def count_message_tokens(self, messages: list[dict[str, str]]) -> int:
        """Count a formatted prompt; remote engines use a conservative fallback."""
        if has_attachments(messages):
            return self.count_attachment_message_tokens(messages)
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
