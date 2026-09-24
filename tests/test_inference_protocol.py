from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.inference import (
    InferenceEngine,
    ModelCapabilityDefinition,
    ModelProtocolFailureCode,
    ModelResponse,
    ModelResponseKind,
)
from app.inference.protocol import (
    model_capability_definitions,
    model_capability_calls_message,
    model_capability_result_message,
    native_chat_messages,
    native_function_tools,
    normalize_native_chat_completion,
    normalize_native_chat_message,
)


def definition(name: str = "filesystem.stat") -> ModelCapabilityDefinition:
    return ModelCapabilityDefinition(
        name=name,
        description="Return bounded metadata for one path.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def native_call(
    *,
    call_id: str = "call_native_1",
    name: str | None = None,
    arguments: str = '{"path":"sample.txt"}',
):
    if name is None:
        name = provider_name()
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def provider_name(name: str = "filesystem.stat") -> str:
    return native_function_tools((definition(name),))[0]["function"]["name"]


def neutral_call(call_id: str = "call_native_1"):
    return {
        "provider_call_id": call_id,
        "capability": "filesystem.stat",
        "arguments": {"path": "sample.txt"},
    }


def message(*, content=None, tool_calls=None, **extra):
    value = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }
    value.update(extra)
    return value


def test_native_function_tools_are_strict_deep_copied_and_deterministic():
    first = definition("filesystem.stat")
    second = definition("filesystem.list")
    definitions = model_capability_definitions((first, second), require_nonempty=True)

    tools = native_function_tools(definitions)

    provider_names = [tool["function"]["name"] for tool in tools]
    assert provider_names == [
        provider_name("filesystem.stat"),
        provider_name("filesystem.list"),
    ]
    assert provider_names[0] != provider_names[1]
    assert all(len(name) <= 64 for name in provider_names)
    assert all(name.replace("_", "").isalnum() for name in provider_names)
    assert all(tool["type"] == "function" for tool in tools)
    assert all(tool["function"]["strict"] is True for tool in tools)
    assert all(
        tool["function"]["parameters"]["additionalProperties"] is False
        for tool in tools
    )
    tools[0]["function"]["parameters"]["properties"]["injected"] = {
        "type": "boolean"
    }
    assert "injected" not in first.input_schema["properties"]


def test_native_function_tools_can_omit_strict_for_compatibility():
    tools = native_function_tools((definition(),), include_strict=False)

    assert "strict" not in tools[0]["function"]
    assert tools[0]["function"]["parameters"]["additionalProperties"] is False


def test_definition_snapshot_rejects_empty_duplicate_and_permissive_schemas():
    with pytest.raises(ValueError, match="at least one"):
        model_capability_definitions((), require_nonempty=True)
    with pytest.raises(ValueError, match="duplicate"):
        model_capability_definitions((definition(), definition()))
    with pytest.raises(ValidationError, match="strict objects"):
        ModelCapabilityDefinition(
            name="filesystem.stat",
            description="Unsafe schema",
            input_schema={"type": "object", "properties": {}},
        )


def test_native_assistant_text_is_normalized_without_scraping_tool_like_prose():
    tool_like_prose = (
        'I would call {"name":"filesystem.stat",'
        '"arguments":{"path":"secret.txt"}}.'
    )

    result = normalize_native_chat_message(
        message(content=tool_like_prose),
        (definition(),),
    )

    assert result.kind == ModelResponseKind.ASSISTANT_TEXT
    assert result.assistant_text == tool_like_prose
    assert result.capability_calls == ()


def test_native_text_parts_are_joined_only_from_explicit_content_fields():
    result = normalize_native_chat_message(
        message(
            content=[
                {"type": "text", "text": "First"},
                {"type": "output_text", "text": " second"},
            ]
        ),
        (definition(),),
    )

    assert result.kind == ModelResponseKind.ASSISTANT_TEXT
    assert result.assistant_text == "First second"


def test_invalid_assistant_text_encoding_becomes_a_protocol_failure():
    result = normalize_native_chat_message(
        message(content="invalid-\ud800-text"),
        (definition(),),
    )

    assert result.protocol_failure.code == ModelProtocolFailureCode.MALFORMED_RESPONSE


def test_length_finished_malformed_call_is_reported_as_output_truncation():
    result = normalize_native_chat_completion(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": message(
                        content=None,
                        tool_calls=[native_call(arguments='{"path":"unfinished')],
                    ),
                }
            ]
        },
        (definition(),),
    )

    assert result.protocol_failure.code == ModelProtocolFailureCode.OUTPUT_TRUNCATED


def test_native_calls_preserve_provider_ids_names_and_untrusted_arguments():
    provider_message = message(
        tool_calls=[
            native_call(),
            native_call(
                call_id="call_native_2",
                name=provider_name("filesystem.list"),
                arguments='{"path":".","unexpected":true}',
            ),
        ]
    )

    result = normalize_native_chat_message(
        provider_message,
        (definition(), definition("filesystem.list")),
    )
    provider_message["tool_calls"][0]["function"]["arguments"] = "changed"

    assert result.kind == ModelResponseKind.CAPABILITY_CALLS
    assert [call.provider_call_id for call in result.capability_calls] == [
        "call_native_1",
        "call_native_2",
    ]
    assert result.capability_calls[0].arguments == {"path": "sample.txt"}
    assert [call.capability for call in result.capability_calls] == [
        "filesystem.stat",
        "filesystem.list",
    ]
    # Provider parsing is intentionally separate from capability-schema validation.
    assert result.capability_calls[1].arguments == {
        "path": ".",
        "unexpected": True,
    }


def test_provider_neutral_call_and_result_history_translates_to_native_messages():
    call = normalize_native_chat_message(
        message(tool_calls=[native_call()]),
        (definition(),),
    ).capability_calls[0]
    result = {
        "call_id": "internal-call-1",
        "capability": "filesystem.stat",
        "success": True,
        "output": {"type": "file"},
        "error": None,
        "duration_ms": 1,
        "metadata": {},
    }

    translated = native_chat_messages(
        [
            {"role": "user", "content": "Inspect sample.txt"},
            model_capability_calls_message((call,)),
            model_capability_result_message(call, result),
        ],
        (definition(),),
    )

    assert translated[1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_native_1",
                "type": "function",
                "function": {
                    "name": provider_name(),
                    "arguments": '{"path":"sample.txt"}',
                },
            }
        ],
    }
    assert translated[2]["role"] == "tool"
    assert translated[2]["tool_call_id"] == "call_native_1"
    assert translated[2]["content"] == (
        '{"call_id":"internal-call-1","capability":"filesystem.stat",'
        '"duration_ms":1,"error":null,"metadata":{},'
        '"output":{"type":"file"},"success":true}'
    )


@pytest.mark.parametrize(
    "transcript",
    [
        [
            {"role": "assistant", "capability_calls": [neutral_call()]},
        ],
        [
            {"role": "capability", "provider_call_id": "call_native_1", "capability": "filesystem.stat", "result": {}},
        ],
        [
            {"role": "assistant", "capability_calls": [neutral_call()]},
            {"role": "capability", "provider_call_id": "call_native_1", "capability": "filesystem.list", "result": {}},
        ],
    ],
)
def test_native_transcript_translation_rejects_unpaired_or_mismatched_results(transcript):
    with pytest.raises((ValidationError, ValueError)):
        native_chat_messages(transcript, (definition(),))


@pytest.mark.parametrize(
    ("raw_call", "expected"),
    [
        (
            native_call(call_id="bad id"),
            ModelProtocolFailureCode.MALFORMED_CALL_ID,
        ),
        (
            native_call(name="INVALID NAME"),
            ModelProtocolFailureCode.MALFORMED_CAPABILITY_NAME,
        ),
        (
            native_call(arguments="not-json"),
            ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        ),
        (
            native_call(arguments="[]"),
            ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        ),
        (
            native_call(arguments='{"path":"one","path":"two"}'),
            ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        ),
        (
            native_call(arguments='{"value":NaN}'),
            ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        ),
        (
            native_call(arguments='{"value":"\ud800"}'),
            ModelProtocolFailureCode.MALFORMED_ARGUMENTS,
        ),
        (
            native_call(name=provider_name("filesystem.missing")),
            ModelProtocolFailureCode.UNKNOWN_CAPABILITY,
        ),
        (
            {"id": "call_native_1", "type": "custom", "input": "hello"},
            ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS,
        ),
    ],
)
def test_malformed_native_calls_become_bounded_protocol_failures(
    raw_call,
    expected,
):
    result = normalize_native_chat_message(
        message(tool_calls=[raw_call]),
        (definition(),),
    )

    assert result.kind == ModelResponseKind.PROTOCOL_FAILURE
    assert result.protocol_failure.code == expected
    assert len(result.model_dump_json()) < 1_000
    assert "not-json" not in result.model_dump_json()


def test_mixed_text_and_calls_are_rejected_instead_of_guessing_intent():
    result = normalize_native_chat_message(
        message(content="I will do that", tool_calls=[native_call()]),
        (definition(),),
    )

    assert result.protocol_failure.code == ModelProtocolFailureCode.MIXED_RESPONSE


def test_legacy_function_call_is_rejected_without_prose_or_json_recovery():
    result = normalize_native_chat_message(
        message(
            content=None,
            function_call={
                "name": "filesystem.stat",
                "arguments": '{"path":"sample.txt"}',
            },
        ),
        (definition(),),
    )

    assert (
        result.protocol_failure.code
        == ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS
    )


def test_duplicate_and_excessive_calls_are_rejected_before_any_runtime_step():
    duplicate = normalize_native_chat_message(
        message(tool_calls=[native_call(), native_call()]),
        (definition(),),
    )
    excessive = normalize_native_chat_message(
        message(
            tool_calls=[
                native_call(call_id=f"call_{index}") for index in range(17)
            ]
        ),
        (definition(),),
    )

    assert (
        duplicate.protocol_failure.code
        == ModelProtocolFailureCode.DUPLICATE_CALL_ID
    )
    assert excessive.protocol_failure.code == ModelProtocolFailureCode.TOO_MANY_CALLS


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"choices": []},
        {"choices": [{"message": message(content="one")}, {"message": message(content="two")}]},
        {"choices": [{"message": "not-an-object"}]},
    ],
)
def test_malformed_completion_envelopes_become_protocol_failures(response):
    result = normalize_native_chat_completion(response, (definition(),))

    assert result.protocol_failure.code == ModelProtocolFailureCode.MALFORMED_RESPONSE


def test_fake_provider_response_is_deterministic_and_does_not_mutate_definitions():
    response = {
        "choices": [
            {
                "message": message(
                    tool_calls=[native_call(arguments='{"path":"folder"}')]
                )
            }
        ]
    }
    schema_before = deepcopy(definition().input_schema)
    advertised = definition()

    first = normalize_native_chat_completion(response, (advertised,))
    second = normalize_native_chat_completion(response, (advertised,))

    assert first == second
    assert advertised.input_schema == schema_before


def test_adapter_without_native_support_returns_a_protocol_result():
    class TextOnlyEngine(InferenceEngine):
        def respond(self, messages):
            return "text"

    result = TextOnlyEngine().respond_with_capabilities(
        [{"role": "user", "content": "inspect"}],
        (definition(),),
    )

    assert (
        result.protocol_failure.code
        == ModelProtocolFailureCode.UNSUPPORTED_CAPABILITY_CALLS
    )


def test_non_string_assistant_content_is_not_coerced_into_prose():
    result = ModelResponse.text(42)

    assert result.protocol_failure.code == ModelProtocolFailureCode.MALFORMED_RESPONSE


def test_ui_entry_point_remains_disconnected_from_tool_protocol():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "app/main.py",
        "app/ui/main_window.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "respond_with_capabilities" not in text
        assert "ModelCapabilityDefinition" not in text
        assert "CapabilityRegistry" not in text
        assert "app.capabilities" not in text
