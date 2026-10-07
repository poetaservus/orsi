"""Strict Responses tool boundary; execution and permissions stay in the harness.

Flat tools and exact call/result ID pairing adapt the pinned OpenCode Responses
converters. Explicit strict mode follows OpenAI documentation rather than the
reference's non-strict default. See THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Iterable

from app.capabilities.contracts import CapabilityResult
from app.inference.completion import CompletionMetadata
from app.inference.protocol import (
    ModelCapabilityCall, ModelCapabilityDefinition, ModelProtocolFailureCode,
    ModelResponse, _canonical_json, _json_size, _unique_object,
    model_capability_definitions, native_chat_messages, native_function_tools,
)

_MAX_ARGUMENT_BYTES = 2 * 1024 * 1024
_MAX_DEPTH = 64
_ANNOTATIONS = {"title", "description", "default", "examples", "$schema"}
_KEYWORDS = {"type", "properties", "required", "additionalProperties", "$defs", "$ref",
             "items", "anyOf", "enum", "const", "minLength", "maxLength", "pattern",
             "format", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
             "multipleOf", "minItems", "maxItems"}
_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def _resolve(schema: dict, root: dict) -> dict:
    for _ in range(_MAX_DEPTH):
        reference = schema.get("$ref")
        if reference is None:
            return schema
        if not isinstance(reference, str) or not (reference == "#" or reference.startswith("#/")):
            raise ValueError("OpenAI tool schemas require local JSON references.")
        if set(schema) - _ANNOTATIONS - {"$ref"}:
            raise ValueError("OpenAI tool references cannot have structural siblings.")
        target = root
        for part in reference[2:].split("/") if reference != "#" else ():
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or key not in target:
                raise ValueError("OpenAI tool schema reference cannot be resolved.")
            target = target[key]
        if not isinstance(target, dict):
            raise ValueError("OpenAI tool references must resolve to schemas.")
        schema = target
    raise ValueError("OpenAI tool schema reference chain is too deep.")


def _strict_schema(schema: dict, root: dict, depth: int = 0) -> dict:
    if not isinstance(schema, dict) or depth > _MAX_DEPTH or set(schema) - _KEYWORDS - _ANNOTATIONS:
        raise ValueError("OpenAI tool schema contains unsupported structure.")
    if "$ref" in schema:
        _resolve(schema, root)
    result = {key: deepcopy(value) for key, value in schema.items()
              if key not in _ANNOTATIONS or key == "description"}
    if "const" in result:
        if "enum" in result:
            raise ValueError("OpenAI tool schemas cannot combine const and enum.")
        result["enum"] = [result.pop("const")]
    if "$defs" in result:
        if not isinstance(result["$defs"], dict):
            raise ValueError("OpenAI tool definitions must be schema objects.")
        result["$defs"] = {key: _strict_schema(value, root, depth + 1)
                           for key, value in result["$defs"].items()}
    if "anyOf" in result:
        alternatives = result["anyOf"]
        if not isinstance(alternatives, list) or not alternatives:
            raise ValueError("OpenAI tool unions require schema alternatives.")
        result["anyOf"] = [_strict_schema(value, root, depth + 1) for value in alternatives]
    kinds = result.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if not isinstance(kinds, list) or any(kind not in _TYPES for kind in kinds):
        raise ValueError("OpenAI tool schema has an unsupported type.")
    if "object" in kinds:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if (schema.get("additionalProperties") is not False or not isinstance(properties, dict)
                or not isinstance(required, list) or any(key not in properties for key in required)):
            raise ValueError("OpenAI tool objects must forbid extra fields and declare properties.")
        result["properties"] = {}
        for key, child in properties.items():
            converted = _strict_schema(child, root, depth + 1)
            if key not in required:
                # The wire's null sentinel means 'use the domain default'. The
                # domain schema is retained for decoding and never modified.
                converted = {"anyOf": [converted, {"type": "null"}]}
            result["properties"][key] = converted
        result["required"] = list(properties)
        result["additionalProperties"] = False
    if "array" in kinds:
        if "items" not in schema:
            raise ValueError("OpenAI tool arrays require one item schema.")
        result["items"] = _strict_schema(schema["items"], root, depth + 1)
    if not kinds and "anyOf" not in result and "$ref" not in result:
        raise ValueError("OpenAI tool schemas must have an explicit supported type.")
    return result


def responses_function_tools(definitions: Iterable[ModelCapabilityDefinition]) -> list[dict]:
    values = model_capability_definitions(definitions, require_nonempty=True)
    tools = []
    for definition, native in zip(values, native_function_tools(values), strict=True):
        tool = native["function"]
        tool["parameters"] = _strict_schema(definition.input_schema, definition.input_schema)
        tools.append({"type": "function", **tool})
    return tools


def _arguments(schema: dict, value: Any, root: dict, *, from_wire: bool, depth: int = 0) -> Any:
    """Validate wire shape and undo null sentinels; Pydantic owns value constraints."""
    if depth > _MAX_DEPTH:
        raise ValueError("OpenAI tool arguments exceed the nesting limit.")
    schema = _resolve(schema, root)
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                return _arguments(alternative, value, root, from_wire=from_wire, depth=depth + 1)
            except ValueError:
                pass
        raise ValueError("OpenAI tool argument does not match its declared union.")
    kinds = schema.get("type")
    kinds = [kinds] if isinstance(kinds, str) else kinds
    kind = ("null" if value is None else "boolean" if type(value) is bool else
            "integer" if type(value) is int else "number" if type(value) is float else
            "string" if isinstance(value, str) else "array" if isinstance(value, list) else
            "object" if isinstance(value, dict) else None)
    if kind not in kinds and not (kind == "integer" and "number" in kinds):
        raise ValueError("OpenAI tool argument has an invalid JSON type.")
    if "enum" in schema and not any(type(item) is type(value) and item == value for item in schema["enum"]):
        raise ValueError("OpenAI tool argument is outside its enum.")
    if "const" in schema and (type(schema["const"]) is not type(value) or value != schema["const"]):
        raise ValueError("OpenAI tool argument does not match its constant.")
    if kind == "object":
        properties, required = schema.get("properties", {}), schema.get("required", [])
        if set(value) - set(properties) or (from_wire and set(value) != set(properties)) or any(key not in value for key in required):
            raise ValueError("OpenAI tool arguments contain missing or extra fields.")
        result = {}
        for key, child in properties.items():
            if key not in value:
                result[key] = None
                continue
            if value[key] is None and key not in required:
                try:
                    result[key] = _arguments(child, None, root, from_wire=from_wire, depth=depth + 1)
                except ValueError:
                    if not from_wire:
                        raise
                    continue  # Remove only a synthetic null; keep genuine nullable values.
            else:
                result[key] = _arguments(child, value[key], root, from_wire=from_wire, depth=depth + 1)
        return result
    if kind == "array":
        return [_arguments(schema["items"], item, root, from_wire=from_wire, depth=depth + 1) for item in value]
    return deepcopy(value)


def responses_input(messages: Iterable[dict], definitions: Iterable[ModelCapabilityDefinition], *, model_id=None) -> list[dict]:
    from app.inference.openai_replay import OpenAIReplay, REPLAY_KEY, neutral_messages
    definitions = model_capability_definitions(definitions, require_nonempty=True)
    transcript = tuple(messages)
    plain = neutral_messages(transcript)
    converted = _neutral_responses_input(plain, definitions)
    result, offset, item_ids = [], 0, set()
    latest_user = max((i for i, m in enumerate(plain) if m.get("role") == "user"), default=-1)
    for index, (source, message) in enumerate(zip(transcript, plain, strict=True)):
        width = len(message["capability_calls"]) + int("content" in message) if "capability_calls" in message else 1
        segment = converted[offset:offset + width]
        offset += width
        if REPLAY_KEY in source:
            replay = OpenAIReplay.model_validate(source[REPLAY_KEY])
            raw_calls = [item for item in replay.items() if item["type"] == "function_call"]
            if raw_calls:
                response = normalize_responses_calls(raw_calls, definitions, CompletionMetadata())
                expected = tuple(ModelCapabilityCall.model_validate(call) for call in message.get("capability_calls", []))
                if response.protocol_failure is not None or response.capability_calls != expected:
                    raise ValueError("OpenAI call evidence does not match its settled transcript.")
            elif "capability_calls" in message:
                raise ValueError("OpenAI call evidence is missing its generating calls.")
            if replay.text.strip() != message.get("content", "").strip():
                raise ValueError("OpenAI text evidence does not match its transcript.")
            if model_id is not None and replay.model != model_id:
                if index > latest_user:
                    raise ValueError("An OpenAI tool turn cannot change model during continuation.")
            else:
                segment = replay.items()
                for item in segment:
                    if item["id"] in item_ids:
                        raise ValueError("OpenAI replay items require unique identities.")
                    item_ids.add(item["id"])
        result.extend(segment)
    return result


def _neutral_responses_input(messages: Iterable[dict], definitions: Iterable[ModelCapabilityDefinition]) -> list[dict]:
    values = model_capability_definitions(definitions, require_nonempty=True)
    transcript = tuple(messages)
    if not transcript:
        raise ValueError("OpenAI tool requests require a non-empty transcript.")
    # Reuse existing transcript bounds, scopes and complete call/result pairing,
    # then preserve actual Responses call IDs instead of the chat adapter's scoped IDs.
    try:
        native = native_chat_messages(transcript, values, allow_attachments=True)
        originals = [ModelCapabilityCall.model_validate(call) if isinstance(call, dict) else call
                     for message in transcript for call in message.get("capability_calls", [])]
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("OpenAI tool transcript has invalid shapes, IDs or unresolved call/result pairs.") from None
    ids = [call.provider_call_id for call in originals]
    if len(ids) != len(set(ids)):
        raise ValueError("OpenAI transcripts require unique actual call IDs across responses.")
    originals = iter(originals)
    schemas = {tool["function"]["name"]: definition.input_schema
               for tool, definition in zip(native_function_tools(values), values, strict=True)}
    calls_by_id = {}
    result = []
    for message in native:
        if message["role"] == "assistant" and "tool_calls" in message:
            if message["content"] is not None:
                result.append({"role": "assistant", "content": message["content"]})
            for call in message["tool_calls"]:
                original = next(originals)
                schema = schemas[call["function"]["name"]]
                arguments = _arguments(schema, original.arguments, schema, from_wire=False)
                calls_by_id[call["id"]] = original
                result.append({"type": "function_call", "call_id": original.provider_call_id,
                               "name": call["function"]["name"], "arguments": _canonical_json(arguments)})
        elif message["role"] == "tool":
            original = calls_by_id[message["tool_call_id"]]
            try:
                envelope = CapabilityResult.model_validate_json(message["content"])
            except ValueError:
                raise ValueError("OpenAI tool results require a valid capability result envelope.") from None
            if envelope.capability != original.capability:
                raise ValueError("OpenAI tool result envelope does not match its capability.")
            result.append({"type": "function_call_output", "call_id": original.provider_call_id,
                           "output": _canonical_json(envelope.model_dump(mode="json"))})
        else:
            result.append(message)
    return result


def normalize_responses_calls(items: list[dict], definitions: Iterable[ModelCapabilityDefinition],
                              completion: CompletionMetadata, *, assistant_text: str | None = None,
                              previous_ids: set[str] | None = None) -> ModelResponse:
    values = model_capability_definitions(definitions, require_nonempty=True)
    if completion.incomplete:
        return ModelResponse.failure(ModelProtocolFailureCode.OUTPUT_TRUNCATED,
                                     "Incomplete OpenAI tool calls cannot execute.").model_copy(update={"completion": completion})
    names = {tool["function"]["name"]: definition
             for tool, definition in zip(native_function_tools(values), values, strict=True)}
    if len(items) > 16:
        return ModelResponse.failure(ModelProtocolFailureCode.TOO_MANY_CALLS, "OpenAI returned too many tool calls.").model_copy(update={"completion": completion})
    seen = set(previous_ids or ())
    calls = []
    failure = None
    for item in items:
        identity = item.get("call_id")
        try:
            # Validate the ID without retaining argument contents in an exception.
            ModelCapabilityCall(provider_call_id=identity, capability=values[0].name, arguments={})
        except (TypeError, ValueError):
            failure = ModelProtocolFailureCode.MALFORMED_CALL_ID
            break
        if identity in seen:
            failure = ModelProtocolFailureCode.DUPLICATE_CALL_ID
            break
        seen.add(identity)
        definition = names.get(item.get("name")) if isinstance(item.get("name"), str) else None
        if definition is None:
            failure = ModelProtocolFailureCode.UNKNOWN_CAPABILITY
            break
        raw = item.get("arguments")
        try:
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > _MAX_ARGUMENT_BYTES:
                raise ValueError
            arguments = json.loads(raw, object_pairs_hook=_unique_object,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(arguments, dict) or _json_size(arguments) > _MAX_ARGUMENT_BYTES:
                raise ValueError
            arguments = _arguments(definition.input_schema, arguments, definition.input_schema, from_wire=True)
            calls.append(ModelCapabilityCall(provider_call_id=identity, capability=definition.name, arguments=arguments))
        except (TypeError, ValueError, UnicodeError, RecursionError):
            failure = ModelProtocolFailureCode.MALFORMED_ARGUMENTS
            break
    if failure is not None:
        result = ModelResponse.failure(failure, "OpenAI returned an invalid native tool call; no calls in this response can execute.")
    else:
        result = ModelResponse.calls(tuple(calls), assistant_text=assistant_text)
    return result.model_copy(update={"completion": completion})
