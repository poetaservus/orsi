from __future__ import annotations

from abc import ABC, abstractmethod


class InferenceUnavailable(RuntimeError):
    pass


class InferenceEngine(ABC):
    """Text conversation in, text response out."""

    @abstractmethod
    def respond(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError
