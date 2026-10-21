"""Personal diagnostics preserve incident scope while dropping arbitrary data."""
import json
import logging
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

import pytest

from app.runtime.diagnostic_context import (begin_turn, current_turn_id, end_turn,
    current_request_phase, new_request_id, run_in_turn, safe_local_id)
from app.conversation.diagnostics import record_route, record_turn
from app.inference.openai_diagnostics import event_fingerprint, record_stream_failure
from app.vault.logging import ProfileLogHandler


@pytest.fixture
def personal_log(tmp_path):
    path = tmp_path / "personal-events.json"
    registrations = []
    session = SimpleNamespace(storage_path=lambda _: path,
                              register=lambda **callbacks: registrations.append(callbacks))
    handler = ProfileLogHandler(session)
    yield handler, path, registrations
    handler.close()


def _logger(handler, name):
    # A separate Logger avoids configuring the application's global logging.
    logger = logging.Logger(name, logging.INFO)
    logger.addHandler(handler)
    return logger


def _stream(**changes):
    return SimpleNamespace(**({"last_event": "response.queued", "last_event_supported": True,
        "events": 2, "sequence": 1, "bytes": 123, "chars": 0,
        "request_phase": "completion_review", "observed_function_call": False,
        "turn_id": current_turn_id(), "request_id": new_request_id()} | changes))


def test_profile_retains_route_turn_and_stream_correlation(personal_log):
    handler, path, _ = personal_log
    conversation = _logger(handler, "app.conversation.orchestrator")
    provider = _logger(handler, "app.inference.openai_backend")
    token = begin_turn()
    try:
        turn_id = current_turn_id()
        decision = SimpleNamespace(route="agent", reason="editable_document", source="none", references=())
        record_route(conversation, decision, submitted_count=0, skill_scope="none")
        state = _stream()
        record_stream_failure(provider, state, reason="stream_ended")
        result = SimpleNamespace(status=SimpleNamespace(value="incomplete"),
            completion=SimpleNamespace(failure_reason="stream_ended", request_phase="completion_review",
                                       observed_function_call=False),
            settled_calls=(), steps=4, model_requests=2, capability_calls=1,
            semantic_corrections=0, protocol_failures=1)
        record_turn(conversation, result)
    finally:
        end_turn(token)
    assert current_turn_id() is None
    route, stream, terminal = json.loads(path.read_text())
    assert [row["event"] for row in (route, stream, terminal)] == [
        "route_decision", "openai_stream_failure", "agent_turn"]
    assert {row["turn_id"] for row in (route, stream, terminal)} == {turn_id}
    assert safe_local_id(turn_id) == turn_id
    assert stream["request_id"] == state.request_id
    assert stream["event_type"] == "response.queued" and stream["event_category"] == "lifecycle"
    assert stream["request_phase"] == terminal["request_phase"] == "completion_review"
    assert terminal["protocol_failures"] == 1 and not terminal["observed_function_call"]


def test_unknown_event_fingerprint_survives_without_raw_name(personal_log):
    handler, path, _ = personal_log
    private = "provider.private-sk-proj-secret-file-path"
    fingerprint = event_fingerprint(private)
    state = _stream(last_event="unrecognized", last_event_supported=False,
                    last_event_fingerprint=fingerprint)
    record_stream_failure(_logger(handler, "app.inference.openai_stream"), state,
                          reason="unsupported_event")
    event = json.loads(path.read_text())[0]
    assert event["event_type"] == "unrecognized" and event["event_fingerprint"] == fingerprint
    assert len(fingerprint) == 64 and fingerprint == event_fingerprint(private)
    assert private not in path.read_text() and "sk-proj" not in path.read_text()
    assert event_fingerprint("response.queued") is None
    assert event_fingerprint("x" * 513) is None and event_fingerprint({private: 1}) is None


def test_profile_revalidates_forged_conversation_and_stream_extras(personal_log):
    handler, path, _ = personal_log
    private = "PRIVATE sk-proj-secret /secret/document.docx"
    record = logging.LogRecord("app.conversation.orchestrator", logging.ERROR, private, 0,
                               private + "%s", (private,), (Exception, Exception(private), None))
    record.orsi_conversation_diagnostic = {"event": "route_decision", "route": private,
        "reason": [private], "source": private, "attachments": private,
        "submitted_count": True, "selected_count": -1, "image_count": 10**100,
        "file_count": private, "skill_scope": private, "turn_id": private,
        "prompt": private, "document": private}
    handler.emit(record)
    record.orsi_conversation_diagnostic = {"event": "agent_turn", "terminal_status": private,
        "failure_reason": private, "request_phase": private, "observed_function_call": private,
        "turn_id": "A" * 32, "steps": True, "tool_error_counts": {
            "invalid_arguments": 2, private: 3, "permission_denied": True}, "answer": private}
    handler.emit(record)
    record.name = "app.inference.openai_stream"
    record.orsi_openai_stream_diagnostic = {"reason": "unsupported_event", "origin": "stream",
        "event_type": private, "event_fingerprint": private, "request_phase": [private],
        "turn_id": "1" * 33, "request_id": "g" * 32, "sdk_version": private,
        "events": True, "text_chars": private, "payload": private}
    handler.emit(record)
    route, turn, stream = json.loads(path.read_text())
    assert route["route"] == route["reason"] == "unknown" and route["turn_id"] is None
    assert all(route[field] is None for field in ("submitted_count", "selected_count", "image_count", "file_count"))
    assert turn["tool_error_counts"] == {"invalid_arguments": 2}
    assert turn["request_phase"] == "unknown" and turn["turn_id"] is None
    assert turn["observed_function_call"] is False
    assert stream["event_fingerprint"] is stream["turn_id"] is stream["request_id"] is None
    assert stream["request_phase"] == "unknown"
    assert "PRIVATE" not in path.read_text() and "sk-proj" not in path.read_text()
    assert all("prompt" not in event and "payload" not in event for event in (route, turn, stream))


def test_old_diagnostics_and_bounded_retention_remain_compatible(personal_log):
    handler, path, registrations = personal_log
    record = logging.LogRecord("app.inference.openai_stream", logging.INFO, "", 0, "", (), None)
    # Saved schema before local correlation and phase fields were introduced.
    record.orsi_openai_stream_diagnostic = {"origin": "stream", "reason": "stream_ended",
        "code": "none", "event_type": "response.created", "event_supported": True,
        "sdk_version": "2.54.0", "events": 1, "sequence": 0, "bytes": 50, "text_chars": 0}
    handler.emit(record)
    original = json.loads(path.read_text())[0]
    assert original["reason"] == "stream_ended" and original["request_phase"] == "unknown"
    assert original["turn_id"] is original["request_id"] is None
    for index in range(205):
        record.orsi_openai_stream_diagnostic = {**record.orsi_openai_stream_diagnostic, "events": index}
        handler.emit(record)
    retained = json.loads(path.read_text())
    assert len(retained) == 200 and retained[0]["events"] == 5 and retained[-1]["events"] == 204
    registrations[0]["clear"]()
    handler.emit(record)
    assert len(json.loads(path.read_text())) == 1


def test_turn_context_is_local_and_restored_after_nested_scope():
    assert current_turn_id() is None
    outer = begin_turn()
    outer_id = current_turn_id()
    inner = begin_turn()
    try:
        assert current_turn_id() != outer_id
        assert new_request_id() != new_request_id()
        assert safe_local_id("provider-response-id") is None
    finally:
        end_turn(inner)
    assert current_turn_id() == outer_id
    end_turn(outer)
    assert current_turn_id() is None


def test_owned_thread_carries_only_local_turn_and_always_resets_it():
    unrelated_context = ContextVar("unrelated_private_context", default=None)
    unrelated_token = unrelated_context.set("PRIVATE")
    token = begin_turn()
    try:
        turn_id = current_turn_id()
        with ThreadPoolExecutor(max_workers=1) as worker:
            observed = worker.submit(run_in_turn, turn_id,
                lambda: (current_turn_id(), current_request_phase(), unrelated_context.get()),
                "completion_review").result()
            assert observed == (turn_id, "completion_review", None)
            def failing():
                assert current_turn_id() == turn_id
                assert current_request_phase() == "completion_review"
                raise RuntimeError("Synthetic failure")
            with pytest.raises(RuntimeError):
                worker.submit(run_in_turn, turn_id, failing, "completion_review").result()
            assert worker.submit(current_turn_id).result() is None
            assert worker.submit(current_request_phase).result() == "reply"
            assert worker.submit(run_in_turn, "provider-response-id", current_turn_id).result() is None
            assert worker.submit(run_in_turn, turn_id, current_request_phase, "PRIVATE").result() == "unknown"
            assert worker.submit(current_request_phase).result() == "reply"
        assert current_turn_id() == turn_id
        assert current_request_phase() == "reply"
    finally:
        end_turn(token)
        unrelated_context.reset(unrelated_token)
