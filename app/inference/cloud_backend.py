from __future__ import annotations

import json
import logging
import os
from random import random
from threading import Lock
from time import monotonic, sleep
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.settings.cloud import CloudConfig
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.protocol import (
    ModelCapabilityDefinition,
    ModelResponse,
    model_capability_definitions,
    native_chat_messages,
    native_function_tools,
    normalize_native_chat_completion,
)


log = logging.getLogger(__name__)


class CloudInferenceError(InferenceUnavailable):
    def __init__(
        self,
        message: str,
        *,
        allow_local_fallback: bool = False,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.allow_local_fallback = allow_local_fallback
        self.retryable = retryable


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
        self._model_lock = Lock()
        self._active_model_index = 0

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def set_api_key(self, api_key: str) -> None:
        self._api_key = str(api_key).strip()

    @property
    def active_model(self) -> str:
        with self._model_lock:
            return self.config.model_pool[self._active_model_index]

    def respond(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            raise CloudInferenceError("Cloud inference received an empty conversation.")
        last_error: CloudInferenceError | None = None
        deadline = monotonic() + self.config.model_step_timeout_seconds
        retry_models = self._candidate_models()
        for retry_index in range(self.config.max_retries + 1):
            next_retry: list[str] = []
            for model in retry_models:
                try:
                    message = self._request_message(
                        {
                            "model": model,
                            "messages": messages,
                            "temperature": self.config.temperature,
                            "max_tokens": self.config.max_tokens,
                        },
                        timeout_seconds=self._candidate_timeout(deadline),
                    )
                    content = _response_text(message)
                    if not content or not content.strip():
                        raise CloudInferenceError(
                            "The cloud model returned an empty response. "
                            "Try again or switch to Local.",
                            allow_local_fallback=True,
                        )
                except CloudInferenceError as exc:
                    if not exc.allow_local_fallback:
                        raise
                    last_error = exc
                    if exc.retryable:
                        next_retry.append(model)
                    log.warning(
                        "Cloud model %s was unavailable; trying the next configured model.",
                        model,
                    )
                    continue
                self._pin_model(model)
                return content
            if not next_retry or retry_index >= self.config.max_retries:
                break
            self._wait_before_retry(retry_index + 1, tuple(next_retry), deadline)
            retry_models = tuple(next_retry)
        if last_error is None:
            raise CloudInferenceError("The cloud model pool is empty.")
        raise last_error

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
        last_error: CloudInferenceError | None = None
        last_protocol_response: ModelResponse | None = None
        deadline = monotonic() + self.config.model_step_timeout_seconds
        retry_models = self._candidate_models()
        for retry_index in range(self.config.max_retries + 1):
            next_retry: list[str] = []
            for model in retry_models:
                request_body = dict(body, model=model)
                try:
                    completion = self._request_completion(
                        request_body,
                        timeout_seconds=self._candidate_timeout(deadline),
                    )
                except CloudInferenceError as exc:
                    if not exc.allow_local_fallback:
                        raise
                    last_error = exc
                    if exc.retryable:
                        next_retry.append(model)
                    log.warning(
                        "Cloud model %s was unavailable; trying the next configured model.",
                        model,
                    )
                    continue
                response = normalize_native_chat_completion(completion, definitions)
                if response.protocol_failure is not None:
                    last_protocol_response = response
                    log.warning(
                        "Cloud model %s returned protocol failure %s; "
                        "trying the next configured model.",
                        model,
                        response.protocol_failure.code.value,
                    )
                    continue
                self._pin_model(model)
                return response
            if not next_retry or retry_index >= self.config.max_retries:
                break
            self._wait_before_retry(retry_index + 1, tuple(next_retry), deadline)
            retry_models = tuple(next_retry)
        if last_protocol_response is not None:
            return last_protocol_response
        if last_error is None:
            raise CloudInferenceError("The cloud model pool is empty.")
        raise last_error

    def _candidate_models(self) -> tuple[str, ...]:
        models = self.config.model_pool
        with self._model_lock:
            start = self._active_model_index
        return models[start:] + models[:start]

    def _pin_model(self, model: str) -> None:
        index = self.config.model_pool.index(model)
        with self._model_lock:
            changed = index != self._active_model_index
            self._active_model_index = index
        if changed:
            log.info("Pinned cloud inference to model %s after successful failover.", model)

    def _candidate_timeout(self, deadline: float) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CloudInferenceError(
                "The cloud model pool exceeded its model-step time budget.",
                allow_local_fallback=True,
            )
        return min(float(self.config.timeout_seconds), remaining)

    def _wait_before_retry(
        self,
        retry_number: int,
        models: tuple[str, ...],
        deadline: float,
    ) -> None:
        base = min(2.0 * (2 ** (retry_number - 1)), 30.0)
        delay = base + (base * 0.25 * random())
        if monotonic() + delay >= deadline:
            raise CloudInferenceError(
                "The cloud model pool exceeded its model-step time budget.",
                allow_local_fallback=True,
            )
        log.warning(
            "Retrying %d transiently unavailable cloud model(s) in %.1f seconds.",
            len(models),
            delay,
        )
        sleep(delay)

    def _request_message(
        self,
        body: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        payload = self._request_completion(body, timeout_seconds=timeout_seconds)
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

    def _request_completion(
        self,
        body: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
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
            request_timeout = (
                float(self.config.timeout_seconds)
                if timeout_seconds is None
                else timeout_seconds
            )
            with urlopen(request, timeout=request_timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read(4096)
            message = _api_error_message(raw, exc.reason or "The cloud service rejected the request.")
            if self._api_key:
                message = message.replace(self._api_key, "[REDACTED]")
            retryable = exc.code in {408, 409, 429} or exc.code >= 500
            if exc.code in {401, 403}:
                explanation = "The cloud API key was rejected. Enter a valid key and try again."
                fallback = False
            elif exc.code == 429:
                explanation = "The free cloud-model rate limit has been reached. Try later or switch to Local."
                fallback = True
            else:
                explanation = f"Cloud inference failed with HTTP {exc.code}: {message}"
                fallback = retryable or exc.code in {400, 404, 422}
            raise CloudInferenceError(
                explanation,
                allow_local_fallback=fallback,
                retryable=retryable,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CloudInferenceError(
                "Cloud inference could not connect. Check the internet connection or switch to Local.",
                allow_local_fallback=True,
                retryable=True,
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
