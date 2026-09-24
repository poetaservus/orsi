from __future__ import annotations

from app.inference.diagnostics import completion_diagnostics


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
