from __future__ import annotations

import json
import re
from copy import deepcopy
from enum import StrEnum
from hashlib import sha256
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inference.contracts import ModelCapabilityDefinition
from app.inference.tool_repair import StructuredCallDecodeError, decode_json_object


_CAPABILITY_NAME = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
_PROVIDER_CALL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_FUNCTION_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PROVIDER_FUNCTION_PREFIX = "orsi_"
_PROVIDER_FUNCTION_DIGEST_CHARS = 20
_PROVIDER_FUNCTION_SLUG_CHARS = (
    64
    - len(_PROVIDER_FUNCTION_PREFIX)
    - 1
    - _PROVIDER_FUNCTION_DIGEST_CHARS
)
_MAX_CAPABILITY_DEFINITIONS = 128
_MAX_CAPABILITY_CALLS = 16
_MAX_ARGUMENT_BYTES = 2 * 1024 * 1024
_MAX_ASSISTANT_TEXT_CHARS = 1_000_000
_MAX_RESULT_BYTES = 2 * 1024 * 1024


class ModelCapabilityCall(BaseModel):
    """One validated native model request with still-untrusted arguments."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    provider_call_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=3, max_length=128)
    arguments: dict[str, Any]

    @model_validator(mode="after")
    def validate_call(self):
        if _PROVIDER_CALL_ID.fullmatch(self.provider_call_id) is None:
            raise ValueError("Provider call IDs must use bounded stable identifier syntax.")
        if _CAPABILITY_NAME.fullmatch(self.capability) is None:
            raise ValueError("Capability names must use namespace.name syntax.")
        if _json_size(self.arguments) > _MAX_ARGUMENT_BYTES:
            raise ValueError("Capability arguments exceed the protocol size limit.")
        return self


class ModelProtocolFailureCode(StrEnum):
    UNSUPPORTED_CAPABILITY_CALLS = "unsupported_capability_calls"
    MALFORMED_RESPONSE = "malformed_response"
    MALFORMED_CALL_ID = "malformed_call_id"
    MALFORMED_CAPABILITY_NAME = "malformed_capability_name"
    MALFORMED_ARGUMENTS = "malformed_arguments"
    MIXED_RESPONSE = "mixed_response"
    TOO_MANY_CALLS = "too_many_calls"
    DUPLICATE_CALL_ID = "duplicate_call_id"
    UNKNOWN_CAPABILITY = "unknown_capability"


class ModelProtocolFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    code: ModelProtocolFailureCode
    message: str = Field(min_length=1, max_length=500)
    provider_call_id: str | None = Field(default=None, max_length=128)
    capability: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_safe_identifiers(self):
        if (
            self.provider_call_id is not None
            and _PROVIDER_CALL_ID.fullmatch(self.provider_call_id) is None
        ):
            raise ValueError("Protocol failures cannot retain an unsafe provider call ID.")
        if (
            self.capability is not None
            and _CAPABILITY_NAME.fullmatch(self.capability) is None
        ):
            raise ValueError("Protocol failures cannot retain an unsafe capability name.")
        return self


class ModelResponseKind(StrEnum):
    ASSISTANT_TEXT = "assistant_text"
    CAPABILITY_CALLS = "capability_calls"
    PROTOCOL_FAILURE = "protocol_failure"


class ModelResponse(BaseModel):
    """Exactly one provider-neutral outcome from one model request."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: ModelResponseKind
    assistant_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=_MAX_ASSISTANT_TEXT_CHARS,
    )
    capability_calls: tuple[ModelCapabilityCall, ...] = Field(
        default_factory=tuple,
        max_length=_MAX_CAPABILITY_CALLS,
    )
    protocol_failure: ModelProtocolFailure | None = None

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.kind == ModelResponseKind.ASSISTANT_TEXT:
            valid = (
                self.assistant_text is not None
                and not self.capability_calls
                and self.protocol_failure is None
            )
        elif self.kind == ModelResponseKind.CAPABILITY_CALLS:
            valid = (
                self.assistant_text is None
                and bool(self.capability_calls)
                and self.protocol_failure is None
            )
        else:
            valid = (
                self.assistant_text is None
                and not self.capability_calls
                and self.protocol_failure is not None
            )
        if not valid:
            raise ValueError("A model response must contain exactly one outcome kind.")
        return self

    @classmethod
    def text(cls, content: str) -> ModelResponse:
        if not isinstance(content, str):
            return cls.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The model returned malformed assistant text.",
            )
        text = content.strip()
        if not text:
            return cls.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The model returned no assistant text or capability calls.",
            )
        try:
            text.encode("utf-8")
        except UnicodeError:
            return cls.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The model returned invalid assistant text encoding.",
            )
        if len(text) > _MAX_ASSISTANT_TEXT_CHARS:
            return cls.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The model assistant text exceeded the protocol size limit.",
            )
        return cls(kind=ModelResponseKind.ASSISTANT_TEXT, assistant_text=text)

    @classmethod
    def calls(
        cls,
        calls: tuple[ModelCapabilityCall, ...],
    ) -> ModelResponse:
        return cls(
            kind=ModelResponseKind.CAPABILITY_CALLS,
            capability_calls=calls,
        )

    @classmethod
    def failure(
        cls,
        code: ModelProtocolFailureCode,
        message: str,
        *,
        provider_call_id: str | None = None,
        capability: str | None = None,
    ) -> ModelResponse:
        return cls(
            kind=ModelResponseKind.PROTOCOL_FAILURE,
            protocol_failure=ModelProtocolFailure(
                code=code,
                message=message,
                provider_call_id=provider_call_id,
                capability=capability,
            ),
        )


def model_capability_definitions(
    definitions: Iterable[ModelCapabilityDefinition],
    *,
    require_nonempty: bool = False,
) -> tuple[ModelCapabilityDefinition, ...]:
    """Validate one immutable, duplicate-free definition snapshot."""
    values = tuple(definitions)
    if require_nonempty and not values:
        raise ValueError("Structured model requests require at least one capability definition.")
    if len(values) > _MAX_CAPABILITY_DEFINITIONS:
        raise ValueError("Too many capability definitions were supplied to the model adapter.")
    if not all(isinstance(value, ModelCapabilityDefinition) for value in values):
        raise TypeError("Model adapters accept only ModelCapabilityDefinition objects.")
    names = [value.name for value in values]
    if len(names) != len(set(names)):
        raise ValueError("Model capability definitions cannot contain duplicate names.")
    return values


def native_function_tools(
    definitions: Iterable[ModelCapabilityDefinition],
    *,
    include_strict: bool = True,
) -> list[dict[str, Any]]:
    """Translate definitions to OpenAI/llama.cpp native function tools."""
    values = model_capability_definitions(definitions, require_nonempty=True)
    provider_names = _provider_function_names(values)
    tools = []
    for definition, provider_name in zip(values, provider_names, strict=True):
        function = {
            "name": provider_name,
            "description": definition.description,
            "parameters": deepcopy(definition.input_schema),
        }
        if include_strict:
            function["strict"] = True
        tools.append({
            "type": "function",
            "function": function,
        })
    return tools


def model_capability_calls_message(
    calls: tuple[ModelCapabilityCall, ...],
) -> dict[str, Any]:
    """Create one provider-neutral assistant capability-call transcript item."""
    if (
        not isinstance(calls, tuple)
        or not calls
        or len(calls) > _MAX_CAPABILITY_CALLS
        or not all(isinstance(call, ModelCapabilityCall) for call in calls)
    ):
        raise ValueError("Capability-call transcript items require a bounded non-empty call set.")
    return {
        "role": "assistant",
        "capability_calls": [
            deepcopy(call.model_dump(mode="python"))
            for call in calls
        ],
    }


def model_capability_result_message(
    call: ModelCapabilityCall,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Create one provider-neutral result tied to an exact provider call ID."""
    if not isinstance(call, ModelCapabilityCall):
        raise TypeError("Capability results require a ModelCapabilityCall identity.")
    if not isinstance(result, dict) or _json_size(result) > _MAX_RESULT_BYTES:
        raise ValueError("Capability results must contain a bounded JSON object.")
    return {
        "role": "capability",
        "provider_call_id": call.provider_call_id,
        "capability": call.capability,
        "result": deepcopy(result),
    }


def native_chat_messages(
    messages: Iterable[dict[str, Any]],
    definitions: Iterable[ModelCapabilityDefinition],
) -> list[dict[str, Any]]:
    """Translate a provider-neutral transcript to native chat/tool messages."""
    values = model_capability_definitions(definitions, require_nonempty=True)
    provider_names = dict(
        zip((item.name for item in values), _provider_function_names(values), strict=True)
    )
    translated: list[dict[str, Any]] = []
    outstanding: dict[str, str] = {}
    seen_provider_call_ids: set[str] = set()

    for raw_message in tuple(messages):
        if not isinstance(raw_message, dict):
            raise TypeError("Model transcripts accept only message objects.")
        role = raw_message.get("role")

        if role in {"system", "user"}:
            if outstanding or set(raw_message) != {"role", "content"}:
                raise ValueError("Text messages cannot interrupt an unresolved capability call.")
            translated.append(
                {"role": role, "content": _bounded_message_text(raw_message.get("content"))}
            )
            continue

        if role == "assistant" and "capability_calls" not in raw_message:
            if outstanding or set(raw_message) != {"role", "content"}:
                raise ValueError("Assistant text messages must contain only bounded text.")
            translated.append(
                {
                    "role": "assistant",
                    "content": _bounded_message_text(raw_message.get("content")),
                }
            )
            continue

        if role == "assistant":
            if outstanding or set(raw_message) != {"role", "capability_calls"}:
                raise ValueError("Capability-call messages have an invalid transcript shape.")
            raw_calls = raw_message.get("capability_calls")
            if not isinstance(raw_calls, (list, tuple)) or not raw_calls:
                raise ValueError("Capability-call messages require at least one call.")
            if len(raw_calls) > _MAX_CAPABILITY_CALLS:
                raise ValueError("Capability-call messages exceed the call limit.")
            native_calls: list[dict[str, Any]] = []
            for raw_call in raw_calls:
                call = (
                    raw_call
                    if isinstance(raw_call, ModelCapabilityCall)
                    else ModelCapabilityCall.model_validate(raw_call)
                )
                provider_name = provider_names.get(call.capability)
                if provider_name is None:
                    raise ValueError("A transcript call references an unadvertised capability.")
                if call.provider_call_id in seen_provider_call_ids:
                    raise ValueError("A transcript contains a duplicate provider call ID.")
                seen_provider_call_ids.add(call.provider_call_id)
                outstanding[call.provider_call_id] = call.capability
                native_calls.append(
                    {
                        "id": call.provider_call_id,
                        "type": "function",
                        "function": {
                            "name": provider_name,
                            "arguments": _canonical_json(call.arguments),
                        },
                    }
                )
            translated.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": native_calls,
                }
            )
            continue

        if role == "capability":
            if set(raw_message) != {
                "role",
                "provider_call_id",
                "capability",
                "result",
            }:
                raise ValueError("Capability-result messages have an invalid transcript shape.")
            provider_call_id = raw_message.get("provider_call_id")
            capability = raw_message.get("capability")
            if (
                not isinstance(provider_call_id, str)
                or _PROVIDER_CALL_ID.fullmatch(provider_call_id) is None
                or not isinstance(capability, str)
                or _CAPABILITY_NAME.fullmatch(capability) is None
            ):
                raise ValueError("Capability-result messages contain unsafe identifiers.")
            expected = outstanding.pop(provider_call_id, None)
            if expected is None or expected != capability:
                raise ValueError("A capability result does not match an outstanding call.")
            result = raw_message.get("result")
            if not isinstance(result, dict) or _json_size(result) > _MAX_RESULT_BYTES:
                raise ValueError("Capability-result messages require a bounded JSON object.")
            translated.append(
                {
                    "role": "tool",
                    "tool_call_id": provider_call_id,
                    "content": _canonical_json(result),
                }
            )
            continue

        raise ValueError("The model transcript contains an unsupported message role.")

    if outstanding:
        raise ValueError("Every assistant capability call requires a matching result.")
    return translated


def normalize_native_chat_completion(
    response: Any,
    definitions: Iterable[ModelCapabilityDefinition],
) -> ModelResponse:
    """Normalize an OpenAI-compatible non-streaming chat completion."""
    values = model_capability_definitions(definitions)
    if not isinstance(response, dict):
        return _malformed_response()
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        return _malformed_response()
    choice = choices[0]
    if not isinstance(choice, dict):
        return _malformed_response()
    return normalize_native_chat_message(choice.get("message"), values)


def normalize_native_chat_message(
    message: Any,
    definitions: Iterable[ModelCapabilityDefinition],
) -> ModelResponse:
    """Normalize native message.tool_calls without inspecting assistant prose."""
    values = model_capability_definitions(definitions)
    provider_names = dict(
        zip(_provider_function_names(values), (item.name for item in values), strict=True)
    )
    repaired_names = {
        provider_name.casefold(): capability
        for provider_name, capability in provider_names.items()
    }
    repaired_names.update({item.name.casefold(): item.name for item in values})
    if not isinstance(message, dict):
        return _malformed_response()
    role = message.get("role")
    if role is not None and role != "assistant":
        return _malformed_response()
    if message.get("function_call") is not None:
        return ModelResponse.failure(
            ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS,
            "The model returned a legacy function call instead of native tool calls.",
        )

    content_valid, content = _native_text(message.get("content"))
    if not content_valid:
        return _malformed_response()
    raw_calls = message.get("tool_calls")
    if raw_calls is None:
        raw_calls = []
    if not isinstance(raw_calls, list):
        return _malformed_response()
    if content and content.strip() and raw_calls:
        return ModelResponse.failure(
            ModelProtocolFailureCode.MIXED_RESPONSE,
            "The model returned assistant text and capability calls in the same response.",
        )
    if len(raw_calls) > _MAX_CAPABILITY_CALLS:
        return ModelResponse.failure(
            ModelProtocolFailureCode.TOO_MANY_CALLS,
            "The model returned too many capability calls in one response.",
        )
    if not raw_calls:
        return ModelResponse.text(content or "")

    calls: list[ModelCapabilityCall] = []
    seen_call_ids: set[str] = set()
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict) or raw_call.get("type") != "function":
            return ModelResponse.failure(
                ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS,
                "The model returned an unsupported capability-call type.",
            )
        provider_call_id = raw_call.get("id")
        if (
            not isinstance(provider_call_id, str)
            or _PROVIDER_CALL_ID.fullmatch(provider_call_id) is None
        ):
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_CALL_ID,
                "The model returned a malformed capability-call ID.",
            )
        if provider_call_id in seen_call_ids:
            return ModelResponse.failure(
                ModelProtocolFailureCode.DUPLICATE_CALL_ID,
                "The model returned a duplicate capability-call ID.",
                provider_call_id=provider_call_id,
            )
        seen_call_ids.add(provider_call_id)

        function = raw_call.get("function")
        if not isinstance(function, dict):
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_RESPONSE,
                "The model returned a malformed native capability call.",
                provider_call_id=provider_call_id,
            )
        provider_name = function.get("name")
        if not isinstance(provider_name, str) or not 1 <= len(provider_name) <= 128:
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_CAPABILITY_NAME,
                "The model returned a malformed capability name.",
                provider_call_id=provider_call_id,
            )
        capability = provider_names.get(provider_name)
        if capability is None:
            capability = repaired_names.get(provider_name.casefold())
        if capability is None:
            if _PROVIDER_FUNCTION_NAME.fullmatch(provider_name) is None:
                return ModelResponse.failure(
                    ModelProtocolFailureCode.MALFORMED_CAPABILITY_NAME,
                    "The model returned a malformed capability name.",
                    provider_call_id=provider_call_id,
                )
            return ModelResponse.failure(
                ModelProtocolFailureCode.UNKNOWN_CAPABILITY,
                "The model requested a capability that was not advertised.",
                provider_call_id=provider_call_id,
            )

        arguments = _decode_arguments(function.get("arguments"))
        if arguments is None:
            return ModelResponse.failure(
                ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
                "The model returned malformed capability arguments.",
                provider_call_id=provider_call_id,
                capability=capability,
            )
        calls.append(
            ModelCapabilityCall(
                provider_call_id=provider_call_id,
                capability=capability,
                arguments=deepcopy(arguments),
            )
        )
    return ModelResponse.calls(tuple(calls))


def _native_text(content: Any) -> tuple[bool, str | None]:
    if content is None:
        return True, None
    if isinstance(content, str):
        return True, content
    if not isinstance(content, list):
        return False, None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") not in {
            "text",
            "output_text",
        }:
            return False, None
        text = item.get("text")
        if not isinstance(text, str):
            return False, None
        parts.append(text)
    return True, "".join(parts)


def _provider_function_name(capability: str) -> str:
    """Map one internal dotted name into the bounded native-provider namespace."""
    slug = capability.replace(".", "_")[:_PROVIDER_FUNCTION_SLUG_CHARS]
    digest = sha256(capability.encode("utf-8")).hexdigest()[
        :_PROVIDER_FUNCTION_DIGEST_CHARS
    ]
    return f"{_PROVIDER_FUNCTION_PREFIX}{slug}_{digest}"


def _provider_function_names(
    definitions: tuple[ModelCapabilityDefinition, ...],
) -> tuple[str, ...]:
    names = tuple(_provider_function_name(item.name) for item in definitions)
    if len(names) != len(set(names)):
        raise ValueError("Model capability names collided in the provider namespace.")
    return names


def _decode_arguments(raw: Any) -> dict[str, Any] | None:
    try:
        value, _repaired = decode_json_object(raw)
        if _json_size(value) > _MAX_ARGUMENT_BYTES:
            return None
        return value
    except (StructuredCallDecodeError, UnicodeError, TypeError, ValueError, RecursionError):
        return None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _bounded_message_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Model text messages require non-empty string content.")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Model text messages require valid UTF-8 content.") from exc
    if len(value) > _MAX_ASSISTANT_TEXT_CHARS:
        raise ValueError("Model text messages exceed the transcript size limit.")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Model transcript values must contain bounded JSON data.") from exc


def _json_size(value: Any) -> int:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Protocol values must contain bounded JSON data.") from exc
    return len(encoded)


def _malformed_response() -> ModelResponse:
    return ModelResponse.failure(
        ModelProtocolFailureCode.MALFORMED_RESPONSE,
        "The model returned a malformed structured response.",
    )
