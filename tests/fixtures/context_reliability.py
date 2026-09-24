from __future__ import annotations

from copy import deepcopy


LARGE_CSS_LINE_COUNT = 195
LARGE_CSS_BYTES = 65 * 1024
LARGE_TEXT_LINE_COUNT = 4_001


def large_css_fixture() -> str:
    """Return a stable 65 KiB, 195-line stylesheet without storing private content."""
    prefixes = [
        f'.phase0-component-{index:03d} {{ color: #123456; content: "'
        for index in range(1, LARGE_CSS_LINE_COUNT + 1)
    ]
    suffix = '"; }\n'
    base_size = sum(len(prefix.encode("utf-8")) + len(suffix) for prefix in prefixes)
    padding, remainder = divmod(LARGE_CSS_BYTES - base_size, LARGE_CSS_LINE_COUNT)
    lines = [
        prefix + ("x" * (padding + (1 if index < remainder else 0))) + suffix
        for index, prefix in enumerate(prefixes)
    ]
    value = "".join(lines)
    assert len(value.encode("utf-8")) == LARGE_CSS_BYTES
    assert len(value.splitlines()) == LARGE_CSS_LINE_COUNT
    return value


def large_text_fixture() -> str:
    """Return stable content extending beyond the current 1,000-line read ceiling."""
    return "".join(
        f"phase0-line-{index:04d}\n"
        for index in range(1, LARGE_TEXT_LINE_COUNT + 1)
    )


def repeated_tool_history_fixture(repetitions: int = 30) -> list[dict]:
    """Return repeated structured results representative of a long agent session."""
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("Fixture repetitions must be a positive integer.")
    messages: list[dict] = []
    for index in range(1, repetitions + 1):
        provider_call_id = f"phase0-read-{index}"
        messages.extend(
            (
                {
                    "role": "assistant",
                    "content": None,
                    "capability_calls": [
                        {
                            "provider_call_id": provider_call_id,
                            "capability": "filesystem.read_text",
                            "arguments": {"path": f"C:\\fixture\\note-{index}.txt"},
                        }
                    ],
                },
                {
                    "role": "capability",
                    "provider_call_id": provider_call_id,
                    "capability": "filesystem.read_text",
                    "result": {
                        "success": True,
                        "output": {
                            "text": f"bounded fixture result {index} " + ("x" * 256),
                            "content_is_untrusted": True,
                        },
                    },
                },
            )
        )
    return deepcopy(messages)


def provider_context_overflow_fixture() -> dict:
    """Return a content-free provider rejection for later classification tests."""
    return {
        "status": 400,
        "error": {
            "type": "invalid_request_error",
            "code": "context_length_exceeded",
        },
    }
