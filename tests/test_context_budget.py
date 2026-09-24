from __future__ import annotations

import json
from math import ceil

from app.conversation.context import (
    ContextBudget,
    calculate_context_budget,
    capability_schema_reserve,
    select_context_request,
)
from app.inference.contracts import ModelCapabilityDefinition
from tests.fixtures.context_reliability import (
    LARGE_CSS_BYTES,
    LARGE_CSS_LINE_COUNT,
    LARGE_TEXT_LINE_COUNT,
    large_css_fixture,
    large_text_fixture,
    provider_context_overflow_fixture,
    repeated_tool_history_fixture,
)


class ExactCharacterTokenizer:
    context_length = 2_000
    max_response_tokens = 200

    @staticmethod
    def count_message_tokens(messages):
        return sum(len(message["content"]) for message in messages)


class ConservativeSixteenKTokenizer:
    context_length = 16_384
    max_response_tokens = 512

    @staticmethod
    def count_message_tokens(messages):
        characters = sum(len(message["content"]) for message in messages)
        return max(1, ceil(characters / 4) + 4 * len(messages) + 3)


def test_context_budget_is_numeric_content_free_and_additive():
    messages = [
        {"role": "system", "content": "S" * 100},
        {"role": "user", "content": "U" * 200},
        {
            "role": "assistant",
            "content": None,
            "capability_calls": [
                {
                    "provider_call_id": "call-1",
                    "capability": "filesystem.stat",
                    "arguments": {"path": "C:\\fixture\\note.txt"},
                }
            ],
        },
        {
            "role": "capability",
            "provider_call_id": "call-1",
            "capability": "filesystem.stat",
            "result": {"success": True, "output": {"size_bytes": 42}},
        },
    ]

    budget = calculate_context_budget(
        ExactCharacterTokenizer(),
        messages,
        reserved_tokens=75,
        safety_buffer=25,
    )

    assert isinstance(budget, ContextBudget)
    assert budget.system_message_tokens == 100
    assert budget.conversation_tokens == 200
    assert budget.structured_tool_history_tokens > 0
    assert budget.requested_output_reserve == 200
    assert budget.capability_schema_reserve == 75
    assert budget.safety_buffer == 25
    assert budget.total_estimated_request_tokens == (
        budget.system_message_tokens
        + budget.conversation_tokens
        + budget.structured_tool_history_tokens
        + budget.capability_schema_reserve
        + budget.requested_output_reserve
        + budget.safety_buffer
    )
    assert all(type(value) is int for value in budget.diagnostic_values().values())
    assert "fixture" not in json.dumps(budget.diagnostic_values())


def test_context_selection_returns_the_exact_budget_used_for_admission():
    request = select_context_request(
        ExactCharacterTokenizer(),
        system_prompt="system",
        history=[{"role": "user", "content": "A" * 2_000}],
        reserved_tokens=50,
        safety_buffer=25,
    )

    recalculated = calculate_context_budget(
        ExactCharacterTokenizer(),
        request.messages,
        reserved_tokens=50,
        safety_buffer=25,
    )
    assert request.budget == recalculated
    assert request.budget.fits
    assert request.messages[-1]["content"].startswith("[Earlier content truncated]")


def test_large_css_fixture_reproduces_whole_file_context_pressure():
    css = large_css_fixture()
    structured_write = {
        "role": "assistant",
        "content": None,
        "capability_calls": [
            {
                "provider_call_id": "phase0-css-write",
                "capability": "filesystem.write_text",
                "arguments": {"path": "C:\\fixture\\styles.css", "text": css},
            }
        ],
    }

    budget = calculate_context_budget(
        ConservativeSixteenKTokenizer(),
        [
            {"role": "system", "content": "Use strict native capabilities."},
            {"role": "user", "content": "Change one selector."},
            structured_write,
        ],
    )

    assert len(css.encode("utf-8")) == LARGE_CSS_BYTES
    assert len(css.splitlines()) == LARGE_CSS_LINE_COUNT
    assert not budget.fits
    assert budget.structured_tool_history_tokens > 16_000


def test_large_text_fixture_exposes_current_line_ceiling():
    text = large_text_fixture()
    returned = "".join(text.splitlines(keepends=True)[:1_000])

    assert len(text.splitlines()) == LARGE_TEXT_LINE_COUNT
    assert len(returned.splitlines()) == 1_000
    assert returned != text


def test_repeated_results_are_accounted_as_structured_history():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Continue the task."},
        *repeated_tool_history_fixture(),
    ]

    budget = calculate_context_budget(
        ConservativeSixteenKTokenizer(),
        messages,
    )

    assert budget.structured_tool_history_tokens > budget.conversation_tokens
    assert budget.total_estimated_request_tokens > 2_000


def test_large_capability_schema_reserve_is_visible_near_boundary():
    definition = ModelCapabilityDefinition(
        name="fixture.large_schema",
        description="Measure a deterministic near-boundary schema.",
        input_schema={
            "type": "object",
            "properties": {
                "choice": {
                    "type": "string",
                    "enum": [f"fixture-{index}-" + ("x" * 512) for index in range(48)],
                }
            },
            "required": ["choice"],
            "additionalProperties": False,
        },
    )

    reserve = capability_schema_reserve((definition,))
    budget = calculate_context_budget(
        ConservativeSixteenKTokenizer(),
        [{"role": "system", "content": "system"}],
        reserved_tokens=reserve,
    )

    assert 8_000 < reserve < 10_000
    assert budget.capability_schema_reserve == reserve
    assert budget.remaining_tokens < budget.model_context_limit // 2


def test_provider_context_overflow_fixture_is_deterministic_and_content_free():
    fixture = provider_context_overflow_fixture()

    assert fixture == provider_context_overflow_fixture()
    assert fixture["status"] == 400
    assert fixture["error"]["code"] == "context_length_exceeded"
    assert set(fixture["error"]) == {"type", "code"}
