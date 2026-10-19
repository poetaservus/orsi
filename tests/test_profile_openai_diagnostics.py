"""Personal diagnostics retain incident evidence without request/response content."""
import json
import logging
from types import SimpleNamespace

from app.inference.completion import TokenUsage
from app.inference.openai_diagnostics import record_stream_failure
from app.inference.openai_metrics import OpenAIRequestMetrics, record_request_metrics
from app.vault.logging import ProfileLogHandler


def test_profile_retains_provider_stream_failure_and_timing(tmp_path):
    path = tmp_path / "events.json"
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: path, register=lambda **_: None))
    logger = logging.getLogger("app.inference.openai_backend")
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        state = SimpleNamespace(last_event="error", last_event_supported=True, events=9,
                                sequence=8, bytes=1234, chars=0)
        record_stream_failure(logger, state, reason="provider_stream_error", code="server_error")
        record_request_metrics(logger, OpenAIRequestMetrics(outcome="incomplete", attempts=1,
            queue_ms=0, duration_ms=12500, first_event_ms=180, first_text_ms=None),
            TokenUsage(input_tokens=100, output_tokens=20, reasoning_tokens=15))
        events = json.loads(path.read_text())
        assert events[0]["event"] == "openai_stream_failure"
        assert events[0]["reason"] == "provider_stream_error" and events[0]["code"] == "server_error"
        assert events[0]["events"] == 9 and events[0]["bytes"] == 1234
        assert events[1]["event"] == "openai_request_metrics"
        assert events[1]["duration_ms"] == 12500 and events[1]["first_event_ms"] == 180
        assert events[1]["first_text_ms"] is None and events[1]["reasoning_tokens"] == 15
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
        handler.close()


def test_profile_revalidates_forged_diagnostics_and_never_formats_private_content(tmp_path):
    path = tmp_path / "events.json"
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: path, register=lambda **_: None))
    private = "PRIVATE sk-proj-PRIVATE /private/file conversation"
    record = logging.LogRecord("app.inference.openai_backend", logging.ERROR, private, 1,
                               private + "%s", (private,), None)
    record.orsi_openai_stream_diagnostic = {"origin": [private], "reason": private,
        "code": {private: 1}, "event_type": private, "sdk_version": private,
        "events": True, "sequence": 10**100, "bytes": private, "text_chars": -2,
        "message": private, "headers": private, "request": private}
    handler.emit(record)
    del record.orsi_openai_stream_diagnostic
    record.orsi_openai_metrics_diagnostic = {"outcome": [private], "duration_ms": float("nan"),
        "queue_ms": float("inf"), "first_event_ms": True, "attempts": private,
        "input_tokens": -1, "output_tokens": 10**100, "reasoning_tokens": 3,
        "message": private, "request": private}
    handler.emit(record)
    events = json.loads(path.read_text())
    assert events[0]["reason"] == "unknown" and events[0]["code"] == "unrecognized"
    assert events[0]["events"] is events[0]["bytes"] is events[0]["sequence"] is None
    assert events[1]["duration_ms"] is events[1]["queue_ms"] is events[1]["first_event_ms"] is None
    assert events[1]["input_tokens"] is events[1]["output_tokens"] is None
    assert events[1]["reasoning_tokens"] == 3
    assert "PRIVATE" not in path.read_text()
    assert all("headers" not in event and "message" not in event and "request" not in event for event in events)
    handler.close()
