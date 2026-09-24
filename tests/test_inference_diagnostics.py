from __future__ import annotations

import logging

from app.conversation.context import ContextBudget
from app.inference.diagnostics import (
    completion_diagnostics,
    record_completion_diagnostics,
    record_context_budget,
)


def test_completion_diagnostics_extract_only_bounded_metadata():
    payload = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "sensitive response content"},
            }
        ],
        "usage": {"prompt_tokens": 6551, "completion_tokens": 1536},
    }

    assert completion_diagnostics(payload) == ("length", 6551, 1536)


def test_completion_diagnostics_reject_invalid_metadata_types():
    assert completion_diagnostics(
        {
            "choices": [{"finish_reason": 42}],
            "usage": {"prompt_tokens": True, "completion_tokens": "1536"},
        }
    ) == (None, None, None)
    assert completion_diagnostics(None) == (None, None, None)
    assert completion_diagnostics(
        {"usage": {"prompt_tokens": -1, "completion_tokens": -2}}
    ) == (None, None, None)
    assert completion_diagnostics(
        {"choices": [{"finish_reason": "stop\nPRIVATE-CONTENT"}]}
    ) == (None, None, None)


def test_completion_diagnostics_log_only_bounded_metadata(caplog):
    logger = logging.getLogger("tests.completion-diagnostics")
    payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "PRIVATE-COMPLETION-CONTENT"},
            }
        ],
        "usage": {"prompt_tokens": 123, "completion_tokens": 45},
    }

    with caplog.at_level(logging.INFO, logger=logger.name):
        values = record_completion_diagnostics(logger, payload, provider="fixture")

    assert values == ("stop", 123, 45)
    assert "provider=fixture" in caplog.text
    assert "input_tokens=123" in caplog.text
    assert "output_tokens=45" in caplog.text
    assert "PRIVATE-COMPLETION-CONTENT" not in caplog.text


def test_context_budget_log_contains_only_numeric_breakdown(caplog):
    logger = logging.getLogger("tests.context-diagnostics")
    budget = ContextBudget(
        model_context_limit=8_192,
        system_message_tokens=100,
        conversation_tokens=200,
        structured_tool_history_tokens=300,
        capability_schema_reserve=400,
        requested_output_reserve=500,
        safety_buffer=256,
        total_estimated_request_tokens=1_756,
        remaining_tokens=6_436,
    )

    with caplog.at_level(logging.INFO, logger=logger.name):
        record_context_budget(logger, budget, request_kind="fixture-step")

    assert "kind=fixture-step" in caplog.text
    assert "system=100" in caplog.text
    assert "tool_history=300" in caplog.text
    assert "total=1756" in caplog.text
