"""Read error classification and content-free profile diagnostics."""
import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from app.mcp.office_com import OfficeUnavailable
from app.mcp.office_contracts import ReadArguments
from app.mcp.office_read_diagnostics import read_shape, read_call, safe_read_event, record_read_failure, read_failure_message
from app.mcp.office_server import create_live_server
from app.mcp.office_word_render import WordRenderUnavailable
from app.inference.word_plan_diagnostics import record_word_plan
from app.vault.logging import ProfileLogHandler


PRIVATE = "PRIVATE-DOCUMENT-KEY-AND-PATH"


@pytest.mark.parametrize("target,kind", [("authoring", "authoring"), ("layout", "layout"), ("render:4:6", "render"),
    ("text:10:20", "text"), ("table:3", "table"), (PRIVATE, "unknown"), (PRIVATE + "!used", "excel_used")])
def test_argument_shape_never_retains_target_contents(target, kind):
    shape = read_shape({"target": target, "session": PRIVATE, "cursor": PRIVATE})
    assert shape["target_kind"] == kind and shape["cursor"] is True
    assert PRIVATE not in json.dumps(shape)


@pytest.mark.parametrize("error,reason,category", [
    (OfficeUnavailable("Use selection, document or text:start:end for Word."), "unsupported_target", "read_unavailable"),
    (OfficeUnavailable("The Word item cannot fit the read limits."), "read_bound", "read_unavailable"),
    (RuntimeError(PRIVATE), "internal", "read_execution"),
    (OSError(PRIVATE), "io", "read_execution"),
    (WordRenderUnavailable("Use render:first:last without a cursor, with at most three pages per call."), "render_setup", "read_setup"),
])
def test_server_classifies_failures_without_private_exception_text(error, reason, category):
    class STA:
        async def invoke(self, *args):
            read_call("word_piece", lambda: (_ for _ in ()).throw(error))
    async def check():
        server = create_live_server(STA())
        handler = server.get_request_handler("tools/call").handler
        return await handler(None, SimpleNamespace(name="office.read", arguments={"session": "session", "target": "document"}, meta={}))
    output = asyncio.run(check())
    assert output.is_error and output.meta["orsiFailure"] == category
    assert output.meta["orsiReadDiagnostic"]["reason"] == reason
    assert output.meta["orsiReadDiagnostic"]["stage"] == "word_piece"
    assert PRIVATE not in output.model_dump_json()


def test_native_hresult_and_result_validation_are_distinct():
    from app.mcp.office_read_diagnostics import failure_data
    error = RuntimeError(PRIVATE)
    error.hresult = -2147352567
    assert failure_data(error, "read_execute") == {"stage": "read_execute", "reason": "native", "hresult": -2147352567}
    assert failure_data(ValueError(PRIVATE), "result_validation")["reason"] == "invalid_result"


def test_recovery_feedback_includes_supported_word_targets_and_bounded_stage():
    message = read_failure_message({"target": PRIVATE}, {"reason": "unsupported_target", "stage": "word_plan"})
    assert all(t in message for t in ("authoring", "layout", "render:first:last", "unsupported_target", "word_plan"))
    assert len(message) <= 500 and PRIVATE not in message


def test_profile_persists_allowlisted_read_and_word_structure_without_logging_text(tmp_path):
    path = tmp_path / "events.json"
    session = SimpleNamespace(storage_path=lambda name: path, register=lambda **kwargs: None)
    handler = ProfileLogHandler(session)
    read_logger = logging.getLogger("app.mcp.office_read_diagnostics")
    word_logger = logging.getLogger("app.inference.word_plan_diagnostics")
    levels = [logger.level for logger in (read_logger, word_logger)]
    try:
        for logger in (read_logger, word_logger):
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        record_read_failure({"target": "render:4:6", "session": PRIVATE, "cursor": PRIVATE},
            {"stage": "word_render", "reason": "native", "hresult": -2147352567, "message": PRIVATE})
        record_word_plan("decoded_arguments", {"blocks": [{"kind": "paragraph", "text": PRIVATE},
            {"kind": "table", "cells": [[PRIVATE]], "widths_mm": [100]}]})
        forged = logging.LogRecord(read_logger.name, logging.ERROR, PRIVATE, 1, PRIVATE, (), None)
        forged.orsi_read_diagnostic = {"target_kind": [PRIVATE], "stage": {PRIVATE: 1}, "reason": PRIVATE,
            "hresult": PRIVATE, "max_chars": PRIVATE, "message": PRIVATE}
        handler.emit(forged)
        events = json.loads(path.read_text())
        assert events[0]["target_kind"] == "render" and events[0]["first"] == 4 and events[0]["hresult"] == -2147352567
        assert events[1]["shape"]["paragraphs"] == events[1]["shape"]["tables"] == 1
        assert events[1]["shape"]["body_text_chars"] == 2 * len(PRIVATE)
        assert PRIVATE not in path.read_text()
    finally:
        for logger, level in zip((read_logger, word_logger), levels):
            logger.removeHandler(handler)
            logger.setLevel(level)
        handler.close()


def test_diagnostic_event_rejects_arbitrary_fields_and_bounds_numbers():
    event = safe_read_event({"target_kind": PRIVATE, "message": PRIVATE, "first": 10**12, "max_items": True,
        "hresult": 2**64, "cursor": PRIVATE})
    assert event == {"event": "office_read_failure", "target_kind": "unknown", "stage": "bridge", "reason": "unavailable", "cursor": False}


@pytest.mark.parametrize("target,reason,code", [("invalid", "unsupported_target", "invalid_arguments"), ("layout", "native", "invalid_output")])
def test_error_classification_crosses_real_stdio_and_executor(tmp_path, caplog, target, reason, code):
    from tests.test_office_mcp_word import connection
    from tests.test_office_mcp_live import execute
    from tests.test_office_mcp_capabilities import runtime_for
    bridge = connection("read_failure")
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        result = execute(runtime, "read", {"session": session, "target": target}, "read-failure")
        assert not result.success and result.error.code.value == code
        assert reason in result.error.message and "stage=word_plan" in result.error.message
        assert bridge.diagnostics["read_failure"]["reason"] == reason
        assert bridge.diagnostics["read_failure"]["target_kind"] == ("layout" if target == "layout" else "unknown")
        assert "SECRET-COM-DESCRIPTION" not in result.model_dump_json() + json.dumps(bridge.diagnostics) + caplog.text
        assert bridge.exposure.ready
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


@pytest.mark.parametrize("corrected", [True, False])
def test_agent_receives_actionable_read_feedback_and_identical_invalid_retries_still_stop(tmp_path, corrected):
    from app.agent.contracts import AgentRunStatus
    from app.inference.protocol import ModelCapabilityCall, ModelResponse
    from tests.test_bounded_edit_recovery import RoomyScriptedModel
    from tests.test_office_mcp_word import connection
    from tests.test_office_mcp_live import execute
    from tests.test_office_mcp_capabilities import ROOT, runtime_for
    bridge = connection("read_failure")
    model = RoomyScriptedModel([], auto_review=False)
    model.mode = "cloud"
    runtime = runtime_for(bridge, tmp_path, model, policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        targets = ["invalid", "document"] if corrected else ["invalid"] * 3
        model.responses = [ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"provider-{i}",
            capability="office.read", arguments={"session": session, "target": target}),)) for i, target in enumerate(targets)]
        if corrected:
            model.responses.append(ModelResponse.text("Synthetic corrected read completed"))
        outcome = runtime.run([{"role": "user", "content": "Synthetic read recovery regression."}],
            session_id="test-session", turn_id="test-turn", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert outcome.status == (AgentRunStatus.COMPLETED if corrected else AgentRunStatus.REPEATED_CALL)
        feedback = [m["result"] for m in model.requests[1] if m.get("role") == "capability"][-1]
        assert "unsupported_target" in feedback["error"]["message"]
        assert all(target in feedback["error"]["message"] for target in ("authoring", "layout", "render:first:last"))
        assert len(outcome.settled_calls) == 2 and outcome.semantic_corrections == (1 if corrected else 2)
        assert outcome.settled_calls[-1].result.success is corrected
    finally:
        runtime.shutdown()
