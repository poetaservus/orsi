"""Content-free diagnostics at real service and SDK boundaries; no live provider."""
import json
import logging
import os
from importlib.metadata import version

import pytest

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.completion import IncompleteResponseError
from tests.test_cloud_attachment_input import native_sdk
from tests.test_image_generation import image_payload
from tests.test_openai_phase1 import response
from tests.test_openai_streaming import make_engine, Stream, events, streaming_response
from tests.test_routing_intent_fix import make_service
from tests.test_attachment_processing import image_data
from tests.test_bounded_edit_recovery import make_service as recovery_service


def editing_service(engine, tmp_path):
    from app.agent.bootstrap import build_agent_runtime
    from app.runtime.skills import SkillRegistry
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import load_agent_feature_config

    portable = tmp_path / "portable"
    portable.mkdir()
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(engine,
        config=load_agent_feature_config().model_copy(update={"full_local_read_enabled": True}),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    return ConversationService(engine, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
        portable_root=portable, allowed_read_roots=(tmp_path,), host_access_policy=policy,
        skill_registry=SkillRegistry(global_root=tmp_path / "skills"))


def records(caplog, prefix):
    return [json.loads(r.getMessage()[len(prefix) + 1:]) for r in caplog.records
            if r.getMessage().startswith(prefix + " ")]


@pytest.mark.parametrize("scope", ["none", "message", "session"])
@pytest.mark.parametrize("visual", [False, True])
def test_worker_route_and_terminal_records_preserve_decision_and_exclude_content(native_sdk, tmp_path, caplog, scope, visual):
    engine, _, _, _ = native_sdk(payloads=[image_payload() if visual else response("PRIVATE-ANSWER")])
    service = make_service(engine, tmp_path, skills=scope != "none")
    attachment = service.store.attachment_store.import_bytes(image_data(), name="PRIVATE-ATTACHMENT.png")
    prompt = "Generate a photograph of a forest, PRIVATE-PROMPT." if visual else "Fix PRIVATE-SOURCE.py."
    if scope == "session":
        service.activate_skill("python-coder")
    kwargs = {"skill_name": "python-coder"} if scope == "message" else {}
    try:
        with caplog.at_level(logging.INFO):
            decision = service.image_route_decision(prompt, attachments=(attachment,), **kwargs)
            assert not records(caplog, "[route]")  # UI preview is not execution.
            answer = service.run(prompt, attachments=(attachment,), **kwargs)
        route = records(caplog, "[route]")
        terminal = records(caplog, "[turn]")
        assert len(route) == len(terminal) == 1
        assert route[0] == {"route": decision.route, "reason": decision.reason,
            "source": "submitted", "attachments": "image", "submitted_count": 1,
            "selected_count": 1, "image_count": 1, "file_count": 0, "skill_scope": scope}
        assert terminal[0]["terminal_status"] == "completed"
        assert terminal[0]["capability_calls"] == terminal[0]["settled_calls"] == 0
        assert terminal[0]["semantic_corrections"] == 0 and terminal[0]["tool_error_counts"] == {}
        assert not any(token in caplog.text for token in (
            "PRIVATE-PROMPT", "PRIVATE-SOURCE", "PRIVATE-ANSWER", "PRIVATE-ATTACHMENT",
            attachment.sha256, str(tmp_path)))
        assert (service.active_skill is not None) == (scope == "session")
        assert bool(answer.generated_images) == visual
    finally:
        service.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows edit and journal authority")
def test_settled_edit_then_unsupported_stream_never_replays_saved_work(make_engine, tmp_path, caplog):
    from tests.test_openai_tools import function
    requests, streams, payloads, approvals = [], [], [], []
    def handle(request):
        requests.append(request)
        stream = Stream(payloads.pop(0))
        streams.append(stream)
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=3)
    service = editing_service(engine, tmp_path)
    target = tmp_path / "main.py"
    target.write_bytes(b"old\n")
    definition = next(d for d in service.agent_runtime.registry.model_definitions() if d.name == "filesystem.edit_text")
    def approve(record):
        approvals.append(record)
        assert record.capability == "filesystem.edit_text" and target.read_bytes() == b"old\n"
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    payloads.extend([events(response(output=[function(definition, {"path": str(target), "old_text": "old", "new_text": "new",
        "replace_all": False, "expected_sha256": None})])),
        [events()[0], {"type": "response.web_search_call.in_progress", "sequence_number": 1,
            "item_id": "PRIVATE-ITEM", "output_index": 0}]])
    try:
        with caplog.at_level(logging.INFO), pytest.raises(IncompleteResponseError):
            service.run("Fix main.py.")
        terminal = records(caplog, "[turn]")[-1]
        assert terminal["successful_calls"] == terminal["settled_calls"] == 1
        assert terminal["failure_reason"] == "unsupported_event"
        assert terminal["semantic_corrections"] == 0
        assert len(requests) == 2 and len(approvals) == 1
        assert target.read_bytes() == b"new\n" and all(s.closed.is_set() for s in streams)
        restored = ConversationStore(service.store.path)
        assert len(restored.turns()[-1].settled_calls) == 1
        assert restored.turns()[-1].settled_calls[0].result.success
        assert len(service.agent_runtime.executor.journal.records) == 1
        assert len(requests) == 2 and target.read_bytes() == b"new\n"
    finally:
        service.shutdown()


def test_application_log_excludes_raw_provider_records_at_every_level(tmp_path, monkeypatch):
    from app.infrastructure.logging import configure_logging
    owner = logging.Logger("isolated-log-owner")
    monkeypatch.setattr(logging, "getLogger", lambda name=None: owner)
    path = tmp_path / "safe.log"
    configure_logging(path)
    try:
        for name in ("openai", "openai._base_client", "httpx", "httpcore.http11"):
            for level in (logging.DEBUG, logging.INFO, logging.ERROR):
                owner.handle(logging.LogRecord(name, level, "PRIVATE-PATH", 0,
                    "PRIVATE-PROMPT PRIVATE-PATCH sk-proj-PRIVATE-KEY", (), None))
        owner.handle(logging.LogRecord("app.inference.openai_stream", logging.WARNING, "", 0,
            "SAFE-DIAGNOSTIC", (), None))
        for handler in owner.handlers:
            handler.flush()
        text = path.read_text(encoding="utf-8")
        assert "SAFE-DIAGNOSTIC" in text and "PRIVATE" not in text and "sk-proj" not in text
    finally:
        for handler in owner.handlers:
            handler.close()


def test_diagnostic_allowlists_reject_private_types_codes_versions_and_counts(caplog, monkeypatch):
    from types import SimpleNamespace
    from app.inference import openai_diagnostics as diagnostics
    from app.conversation.diagnostics import record_route
    diagnostics.sdk_version.cache_clear()
    monkeypatch.setattr(diagnostics, "version", lambda _: "2.54.0-PRIVATE-KEY")
    state = SimpleNamespace(last_event={"PRIVATE": "EVENT"}, last_event_supported="PRIVATE",
        events=True, sequence=-1, bytes="PRIVATE", chars=10**100)
    decision = SimpleNamespace(route="PRIVATE", reason=["PRIVATE"], source="PRIVATE", references=())
    try:
        with caplog.at_level(logging.INFO):
            diagnostics.record_stream_failure(logging.getLogger(__name__), state, origin=["PRIVATE"],
                reason="PRIVATE", code={"PRIVATE": "CODE"})
            record_route(logging.getLogger(__name__), decision, submitted_count=True, skill_scope="PRIVATE")
        stream = records(caplog, "[stream]")[-1]
        assert stream["sdk_version"] == stream["reason"] == stream["origin"] == "unknown"
        assert stream["code"] == stream["event_type"] == "unrecognized"
        assert stream["events"] is stream["bytes"] is stream["text_chars"] is None
        assert records(caplog, "[route]")[-1]["submitted_count"] is None
        assert "PRIVATE" not in caplog.text
    finally:
        diagnostics.sdk_version.cache_clear()


def test_implicit_image_source_category_does_not_retain_identity(native_sdk, tmp_path, caplog):
    engine, _, _, _ = native_sdk(payloads=[image_payload(), image_payload()])
    service = make_service(engine, tmp_path)
    try:
        original = service.run("Draw a blue circle").generated_images[0]
        with caplog.at_level(logging.INFO):
            service.run("Make the background darker")
        route = records(caplog, "[route]")[-1]
        assert route["source"] == "current_visual_task" and route["selected_count"] == 1
        assert route["submitted_count"] == 0 and route["attachments"] == "image"
        assert original.sha256 not in caplog.text
    finally:
        service.shutdown()


@pytest.mark.parametrize("kind,category", [
    ("response.web_search_call.in_progress", "provider_tool"),
    ("response.audio.delta", "audio"),
    ("response.queued", "lifecycle"),
    ("PRIVATE-EVENT-sk-proj-secret", "unknown"),
])
def test_unsupported_event_records_public_type_and_sdk_version_without_accepting_it(make_engine, caplog, kind, category):
    values = events()[:1] + [{"type": kind, "sequence_number": 1,
        "delta": "PRIVATE-PAYLOAD", "item_id": "PRIVATE-ITEM"}]
    stream = Stream(values)
    requests = []
    def handle(request):
        requests.append(request)
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=3)
    with caplog.at_level(logging.INFO), pytest.raises(IncompleteResponseError) as caught:
        engine.respond([{"role": "user", "content": "PRIVATE-PROMPT"}])
    assert caught.value.completion.failure_reason == "unsupported_event"
    diagnostic = records(caplog, "[stream]")[-1]
    assert diagnostic["event_type"] == ("unrecognized" if category == "unknown" else kind)
    assert diagnostic["event_category"] == category and diagnostic["event_supported"] is False
    assert diagnostic["sdk_version"] == version("openai")
    assert diagnostic["reason"] == "unsupported_event" and diagnostic["events"] == 2
    assert len(requests) == 1 and stream.closed.is_set()
    assert not any(token in caplog.text for token in ("PRIVATE", "sk-proj-secret"))


@pytest.mark.skipif(os.name != "nt", reason="Native Windows edit validation")
def test_sdk_envelope_and_invalid_tool_arguments_are_separate_domains(make_engine, tmp_path, caplog):
    from tests.test_openai_tools import function

    service = None
    streams, requests = [], []
    payloads = []
    def handle(request):
        requests.append(request)
        stream = Stream(payloads.pop(0))
        streams.append(stream)
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=3)
    service = editing_service(engine, tmp_path)
    runtime, store = service.agent_runtime, service.store
    target = tmp_path / "main.py"
    target.write_bytes(b"old\n")
    definition = next(d for d in runtime.registry.model_definitions() if d.name == "filesystem.edit_text")
    payloads.extend([events(response(output=[function(definition, {"path": str(target),
        "old_text": "PRIVATE-MISSING", "new_text": "PRIVATE-PATCH", "replace_all": False, "expected_sha256": None})])),
        [events()[0], {"error": {"code": "server_error", "message": "PRIVATE-ERROR", "param": "PRIVATE-PARAM"}}]])
    try:
        with caplog.at_level(logging.INFO), pytest.raises(IncompleteResponseError):
            service.run("PRIVATE-PROMPT")
        terminal = records(caplog, "[turn]")[-1]
        assert terminal["tool_error_counts"] == {"invalid_arguments": 1}
        assert terminal["semantic_corrections"] == 1
        assert terminal["failure_reason"] == "provider_unavailable"
        assert terminal["terminal_status"] == "incomplete"
        envelope = [r for r in records(caplog, "[stream]") if r["origin"] == "sdk_envelope"]
        assert envelope[-1]["code"] == "server_error"
        assert envelope[-1]["reason"] == "provider_unavailable"
        assert len(requests) == 2 and all(s.closed.is_set() for s in streams)
        assert not any(token in caplog.text for token in ("PRIVATE", str(tmp_path)))
        restored = ConversationStore(store.path)
        assert restored.turns()[-1].outcome.semantic_corrections == 1
        assert len(restored.turns()[-1].settled_calls) == 1
        assert len(requests) == 2
        assert target.read_bytes() == b"old\n"
    finally:
        service.shutdown()


@pytest.mark.parametrize("partial", [False, True])
def test_provider_terminal_retains_only_public_code_and_event(make_engine, caplog, partial):
    from app.inference.cloud_errors import CloudInferenceError
    payload = response("PRIVATE-ANSWER", status="failed",
        error={"code": "server_error", "message": "PRIVATE-ERROR", "param": "PRIVATE-PARAM"})
    if not partial:
        payload["output"] = []
    stream = Stream(events(payload))
    requests = []
    def handle(request):
        requests.append(request)
        return streaming_response(stream)
    engine = make_engine(handle, max_retries=3)
    with caplog.at_level(logging.INFO), pytest.raises((CloudInferenceError, IncompleteResponseError)):
        engine.respond([{"role": "user", "content": "PRIVATE-PROMPT"}])
    diagnostic = next(r for r in records(caplog, "[stream]") if r["origin"] == "provider_terminal")
    assert diagnostic["code"] == "server_error" and diagnostic["reason"] == "provider_unavailable"
    assert diagnostic["event_type"] == "response.failed" and diagnostic["event_supported"] is True
    assert diagnostic["event_category"] == "lifecycle" and diagnostic["sdk_version"] == version("openai")
    assert len(requests) == 1 and stream.closed.is_set() and "PRIVATE" not in caplog.text


@pytest.mark.skipif(os.name != "nt", reason="Native Windows stop and journal authority")
@pytest.mark.parametrize("cancel", [False, True])
def test_terminal_stop_counts_match_durable_settled_work(recovery_service, tmp_path, caplog, cancel):
    from app.inference.protocol import ModelResponse
    from tests.test_bounded_edit_recovery import edit, read
    target = tmp_path / "main.py"
    target.write_bytes(b"old")
    responses = [edit(1, target, "old", "new"), read(2, target)] if cancel else [
        edit(1, target, "missing-1", "new"), read(2, target),
        edit(3, target, "missing-2", "newer"), read(4, target), edit(5, target, "missing-3", "newest")]
    service, model, approvals = recovery_service(responses, mode="cloud")
    if cancel:
        model.before_request[1] = lambda *_: service.cancel_current_task()
    with caplog.at_level(logging.INFO):
        if cancel:
            service.run("Fix main.py.")
        else:
            with pytest.raises(IncompleteResponseError):
                service.run("Fix main.py.")
    terminal = records(caplog, "[turn]")[-1]
    assert terminal["terminal_status"] == ("cancelled" if cancel else "repeated_call")
    assert terminal["semantic_corrections"] == (0 if cancel else 3)
    assert terminal["tool_error_counts"] == ({} if cancel else {"invalid_arguments": 3})
    assert terminal["settled_calls"] == (1 if cancel else 5)
    assert terminal["successful_calls"] == (1 if cancel else 2)
    assert terminal["failed_calls"] == (0 if cancel else 3)
    restored = ConversationStore(service.store.path)
    assert terminal["terminal_status"] == restored.turns()[-1].outcome.status.value
    assert len(restored.turns()[-1].settled_calls) == terminal["settled_calls"]
    before = len(approvals)
    model.responses += [ModelResponse.text("Saved work retained. Execution unrun.")]
    service.run("What happened?")
    assert len(approvals) == before and target.read_bytes() == (b"new" if cancel else b"old")
