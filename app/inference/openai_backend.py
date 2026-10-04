"""OpenAI Responses text and non-reasoning native tools. Item replay follows in 2.2.

Responses selection, capability-gated sampling and disabled response storage
port the corresponding OpenCode implementation choices; see THIRD_PARTY_NOTICES.
OpenAI documentation is authoritative for request and response semantics.
"""
from __future__ import annotations

import logging
import os
from math import ceil
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from app.inference.cloud_backend import CloudErrorCode, CloudInferenceError
from app.inference.completion import CompletionMetadata, CompletionText, IncompleteResponseError, TokenUsage
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelCapabilityDefinition, ModelResponse, ModelProtocolFailureCode, model_capability_definitions
from app.inference.openai_tools import responses_function_tools, responses_input, normalize_responses_calls
from app.settings.openai_cloud import OpenAICloudConfig, OpenAIModelCatalog


log = logging.getLogger(__name__)
_MAX_TEXT_CHARS = 1_000_000
_CONTEXT_ERROR_CODES = {"context_length_exceeded", "context_window_exceeded", "input_too_long"}
_QUOTA_ERROR_CODES = {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active"}


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _error_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error", payload)
    return error.get("code") if isinstance(error, dict) and isinstance(error.get("code"), str) else None


def _provider_error(status: int | None, code: str | None) -> CloudInferenceError:
    # Provider exception messages and bodies are content-bearing; never forward
    # or log them. Error classification uses only known codes and HTTP status.
    if code in _CONTEXT_ERROR_CODES:
        kind, message, retryable, fallback = CloudErrorCode.CONTEXT_OVERFLOW, "The OpenAI request exceeds the model's context limit.", False, False
    elif code in _QUOTA_ERROR_CODES or status == 402:
        kind, message, retryable, fallback = CloudErrorCode.QUOTA, "OpenAI API quota or billing is unavailable. Check the API account.", False, False
    elif status == 401:
        kind, message, retryable, fallback = CloudErrorCode.AUTHENTICATION, "The OpenAI API key was rejected. Enter a valid session key.", False, False
    elif status == 403:
        kind, message, retryable, fallback = CloudErrorCode.PERMISSION, "The OpenAI account cannot access this request or model.", False, False
    elif status == 429:
        kind, message, retryable, fallback = CloudErrorCode.RATE_LIMIT, "OpenAI rate limits were reached. Try again later.", True, True
    elif status in {408, 409} or status is not None and status >= 500:
        kind, message, retryable, fallback = CloudErrorCode.PROVIDER_UNAVAILABLE, "OpenAI is temporarily unavailable. Try again later.", True, True
    else:
        kind, message, retryable, fallback = CloudErrorCode.BAD_REQUEST, "OpenAI rejected the request. Check the configured model and request settings.", False, False
    return CloudInferenceError(message, code=kind, retryable=retryable, allow_local_fallback=fallback)


def _malformed() -> CloudInferenceError:
    return CloudInferenceError("OpenAI returned an invalid Responses payload.", code=CloudErrorCode.MALFORMED_RESPONSE)


def _completion_metadata(payload: dict[str, Any]) -> CompletionMetadata:
    status = payload.get("status")
    if status == "failed":
        raise _provider_error(None, _error_code(payload))
    if not isinstance(status, str) or status not in {"completed", "incomplete", "cancelled"}:
        raise _malformed()
    finish_reason = "stop"
    if status == "incomplete":
        details = payload.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        finish_reason = "length" if reason == "max_output_tokens" else "content_filter" if reason == "content_filter" else "error"
    elif status == "cancelled":
        finish_reason = "cancelled"
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return CompletionMetadata(finish_reason=finish_reason, usage=TokenUsage(
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        total_tokens=_count(usage.get("total_tokens")),
    ))


def normalize_text_response(payload: dict[str, Any]) -> CompletionText:
    completion = _completion_metadata(payload)
    status = payload["status"]
    output = payload.get("output")
    if not isinstance(output, list):
        raise _malformed()
    texts: list[str] = []
    refusals: list[str] = []
    total_chars = 0
    for item in output:
        if not isinstance(item, dict):
            raise _malformed()
        if item.get("type") == "reasoning":
            continue  # Opaque item persistence and replay belong to Phase 2.
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise _malformed()  # No tools were supplied: a call cannot execute.
        if status == "completed" and item.get("status") != "completed":
            raise _malformed()
        content = item.get("content")
        if not isinstance(content, list):
            raise _malformed()
        for part in content:
            if not isinstance(part, dict):
                raise _malformed()
            kind = part.get("type")
            value = part.get("text") if kind == "output_text" else part.get("refusal") if kind == "refusal" else None
            if not isinstance(value, str):
                raise _malformed()
            total_chars += len(value)
            if total_chars > _MAX_TEXT_CHARS:
                raise _malformed()
            (refusals if kind == "refusal" else texts).append(value)
    content = "".join(refusals or texts)
    if not content.strip():
        if completion.incomplete:
            raise IncompleteResponseError("The OpenAI response ended before producing text.", completion)
        raise _malformed()
    if refusals and not completion.incomplete:
        completion = completion.model_copy(update={"finish_reason": "refusal"})
    log.info("OpenAI completion: finish_reason=%s input_tokens=%s output_tokens=%s total_tokens=%s",
             completion.finish_reason, completion.usage.input_tokens,
             completion.usage.output_tokens, completion.usage.total_tokens)
    return CompletionText(content, completion)


def normalize_tool_response(payload: dict[str, Any], definitions, *, previous_ids=None) -> ModelResponse:
    completion = _completion_metadata(payload)
    output = payload.get("output")
    if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
        raise _malformed()
    calls = [item for item in output if item.get("type") == "function_call"]
    messages = [item for item in output if item.get("type") == "message"]
    text = None
    if messages:
        try:
            text = normalize_text_response({**payload, "output": messages})
        except IncompleteResponseError:
            if not completion.incomplete:
                raise
    if completion.incomplete:
        if calls or text is None:
            return ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                "OpenAI ended before completing its tool response; no tool calls can execute.").model_copy(
                    update={"completion": completion, "partial_text": str(text) if text is not None else None})
        return ModelResponse.text(str(text)).model_copy(update={"completion": completion, "partial_text": str(text)})
    if any(item.get("type") not in {"message", "function_call", "reasoning"} for item in output):
        raise _malformed()
    if not calls:
        result = normalize_text_response(payload)
        return ModelResponse.text(str(result)).model_copy(update={"completion": result.completion})
    if any(item.get("type") == "reasoning" for item in output):
        raise CloudInferenceError("OpenAI reasoning tool items require the replay support in Phase 2.2.",
                                  code=CloudErrorCode.TOOLS_NOT_READY)
    if text is not None and text.completion.finish_reason == "refusal":
        return ModelResponse.failure(ModelProtocolFailureCode.MIXED_RESPONSE,
                                    "OpenAI returned both a refusal and tool calls; no calls can execute.").model_copy(
                                        update={"completion": completion})
    if any(item.get("status") is not None and item.get("status") != "completed" for item in calls):
        return ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                                    "OpenAI returned an unfinished tool call; no calls can execute.").model_copy(
            update={"completion": completion.model_copy(update={"finish_reason": "error", "interrupted": True})})
    result = normalize_responses_calls(calls, definitions, completion,
                                      assistant_text=str(text) if text is not None else None,
                                      previous_ids=previous_ids)
    log.info("OpenAI tool completion: outcome=%s call_count=%s input_tokens=%s output_tokens=%s total_tokens=%s",
             result.kind.value, len(result.capability_calls), completion.usage.input_tokens,
             completion.usage.output_tokens, completion.usage.total_tokens)
    return result


class OpenAIResponsesInferenceEngine(InferenceEngine):
    def __init__(self, config: OpenAICloudConfig, api_key: str | None = None, *,
                 selection_path: Path | None = None):
        self.config = config
        self.catalog = OpenAIModelCatalog(config, selection_path)
        self._api_key = (api_key if api_key is not None else os.environ.get(config.api_key_environment, "")).strip()
        self._lock = RLock()
        self._client = None
        self._closed = False
        self._refresh_limits()

    def _refresh_limits(self) -> None:
        profile = self.catalog.current_profile
        self.context_length = profile.effective_context_length
        self.max_response_tokens = profile.max_output_tokens

    @property
    def has_api_key(self) -> bool:
        with self._lock:
            return bool(self._api_key)

    @property
    def active_model(self) -> str:
        with self._lock:
            return self.catalog.current_id

    def select_model(self, model_id: str) -> None:
        with self._lock:
            self._ensure_open()
            self.catalog.select(model_id)
            self._refresh_limits()

    def set_api_key(self, api_key: str) -> None:
        with self._lock:
            self._ensure_open()
            client, self._client = self._client, None
            self._api_key = str(api_key).strip()
            if client is not None:
                client.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise CloudInferenceError("The OpenAI backend is closed.", code=CloudErrorCode.CLOSED)

    def respond(self, messages: list[dict[str, str]]) -> str:
        # Phase 1 supports complete text transcripts only. Reject provider-neutral
        # tool history before any request rather than losing it in conversion.
        if not messages or any(not isinstance(message, dict)
                or set(message) != {"role", "content"}
                or message["role"] not in {"system", "user", "assistant"}
                or not isinstance(message["content"], str) for message in messages):
            raise ValueError("OpenAI text requests require a non-empty text-only transcript.")
        return normalize_text_response(self._request([dict(message) for message in messages]))

    def _request(self, inputs: list[dict], *, tools: list[dict] | None = None) -> dict:
        with self._lock:
            self._ensure_open()
            profile = self.catalog.current_profile
            if tools is not None and profile.reasoning_effort != "none":
                raise CloudInferenceError("OpenAI reasoning tool workflows require the replay support in Phase 2.2.",
                                          code=CloudErrorCode.TOOLS_NOT_READY)
            if not self._api_key:
                raise CloudInferenceError("Cloud mode needs an OpenAI API key for this session.", code=CloudErrorCode.AUTHENTICATION)
            try:
                import openai
            except ImportError:
                raise CloudInferenceError("The OpenAI SDK is missing from this runtime.", code=CloudErrorCode.PROVIDER_UNAVAILABLE) from None
            if self._client is None:
                self._client = openai.OpenAI(api_key=self._api_key, base_url=self.config.base_url,
                                             timeout=self.config.timeout_seconds,
                                             max_retries=self.config.max_retries)
            client = self._client
        body: dict[str, Any] = {
            "model": profile.id,
            "input": inputs,
            "store": False,
            "stream": False,
            "truncation": "disabled",
            "max_output_tokens": profile.max_output_tokens,
            "reasoning": {"effort": profile.reasoning_effort},
        }
        if profile.temperature is not None:
            body["temperature"] = profile.temperature
        if tools is not None:
            body.update(tools=tools, tool_choice="auto", parallel_tool_calls=True)
        # Let the SDK own retries once. Do not wrap it in the old model pool.
        try:
            response = client.responses.create(**body)
            payload = response.model_dump(mode="json")
        except openai.APITimeoutError:
            raise CloudInferenceError("The OpenAI request timed out.", code=CloudErrorCode.TIMEOUT,
                                      retryable=True, allow_local_fallback=True) from None
        except openai.APIConnectionError:
            raise CloudInferenceError("OpenAI could not connect. Check the internet connection.",
                                      code=CloudErrorCode.CONNECTION, retryable=True,
                                      allow_local_fallback=True) from None
        except openai.APIStatusError as exc:
            raise _provider_error(exc.status_code, _error_code(exc.body)) from None
        except (openai.APIError, ValueError, TypeError, AttributeError):
            raise _malformed() from None
        if not isinstance(payload, dict):
            raise _malformed()
        return payload

    def respond_with_capabilities(self, messages: list[dict[str, str]],
                                  capabilities: Iterable[ModelCapabilityDefinition]) -> ModelResponse:
        definitions = model_capability_definitions(capabilities, require_nonempty=True)
        tools = responses_function_tools(definitions)
        inputs = responses_input(messages, definitions)
        previous_ids = {item["call_id"] for item in inputs if item.get("type") == "function_call"}
        return normalize_tool_response(self._request(inputs, tools=tools), definitions, previous_ids=previous_ids)

    def count_capability_schema_tokens(self, definitions) -> int:
        from app.inference.protocol import _canonical_json
        tools = responses_function_tools(definitions)
        # Keep the existing conservative byte-based reserve, using actual wire
        # schemas after strict/nullable conversion instead of domain schemas.
        return ceil(len(_canonical_json(tools).encode("utf-8")) / 3) + 48 * len(tools)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            client, self._client = self._client, None
            self._api_key = ""
        if client is not None:
            client.close()
