from __future__ import annotations

import json
import os
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.inference.cloud_config import CloudConfig
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelResponse,
    model_capability_definitions,
    native_chat_messages,
    native_function_tools,
    normalize_native_chat_completion,
)


class CloudInferenceError(InferenceUnavailable):
    def __init__(self, message: str, *, allow_local_fallback: bool = False):
        super().__init__(message)
        self.allow_local_fallback = allow_local_fallback


def _response_text(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts) or None
    return None


def _api_error_message(raw: bytes, fallback: str) -> str:
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:500]
        if isinstance(error, str):
            return error[:500]
    except (json.JSONDecodeError, UnicodeError):
        pass
    return fallback


class OpenAICompatibleInferenceEngine(InferenceEngine):
    """OpenAI-compatible chat-completions backend with an in-memory API key."""

    def __init__(self, config: CloudConfig, api_key: str | None = None):
        self.config = config
        self.context_length = config.context_length
        self.max_response_tokens = config.max_tokens
        self._api_key = (api_key or os.environ.get(config.api_key_environment, "")).strip()

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def set_api_key(self, api_key: str) -> None:
        self._api_key = str(api_key).strip()

    def respond(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            raise CloudInferenceError("Cloud inference received an empty conversation.")
        message = self._request_message({
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        })
        content = _response_text(message)
        if not content or not content.strip():
            raise CloudInferenceError(
                "The cloud model returned an empty response. Try again or switch to Local.",
                allow_local_fallback=True,
            )
        return content

    def respond_with_capabilities(
        self,
        messages: list[dict[str, str]],
        capabilities: Iterable[ModelCapabilityDefinition],
    ) -> ModelResponse:
        if not messages:
            raise CloudInferenceError("Cloud inference received an empty conversation.")
        definitions = model_capability_definitions(
            capabilities,
            require_nonempty=True,
        )
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": native_chat_messages(messages, definitions),
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "tools": native_function_tools(
                definitions,
                include_strict=self.config.include_tool_strict,
            ),
        }
        if self.config.tool_choice is not None:
            body["tool_choice"] = self.config.tool_choice
        completion = self._request_completion(body)
        return normalize_native_chat_completion(completion, definitions)

    def _request_message(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = self._request_completion(body)
        try:
            choices = payload.get("choices")
            message = choices[0].get("message") if isinstance(choices, list) and choices else None
            if not isinstance(message, dict):
                raise TypeError("missing response message")
        except (AttributeError, IndexError, TypeError) as exc:
            raise CloudInferenceError(
                "The cloud service returned an unreadable response. Try again or switch to Local.",
                allow_local_fallback=True,
            ) from exc
        return message

    def _request_completion(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise CloudInferenceError(
                f"Cloud mode needs a {self.config.provider_name} API key for this session."
            )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Title": "O.R.S.I Chat",
        }
        headers.update(self.config.extra_headers)
        request = Request(
            self.config.chat_completions_url,
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read(4096)
            message = _api_error_message(raw, exc.reason or "The cloud service rejected the request.")
            if self._api_key:
                message = message.replace(self._api_key, "[REDACTED]")
            if exc.code in {401, 403}:
                explanation = "The cloud API key was rejected. Enter a valid key and try again."
                fallback = False
            elif exc.code == 429:
                explanation = "The free cloud-model rate limit has been reached. Try later or switch to Local."
                fallback = True
            else:
                explanation = f"Cloud inference failed with HTTP {exc.code}: {message}"
                fallback = exc.code >= 500
            raise CloudInferenceError(explanation, allow_local_fallback=fallback) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CloudInferenceError(
                "Cloud inference could not connect. Check the internet connection or switch to Local.",
                allow_local_fallback=True,
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("response is not an object")
        except (json.JSONDecodeError, UnicodeError, TypeError) as exc:
            raise CloudInferenceError(
                "The cloud service returned an unreadable response. Try again or switch to Local.",
                allow_local_fallback=True,
            ) from exc
        return payload
