"""Skill lifecycle evidence is bounded, accurate, and content-free at every level."""
from hashlib import sha256
import json
import logging
import os

import pytest

from app.runtime.skills import SkillActivationError, SkillRegistry
from app.runtime.skills.diagnostics import record_skill_event
from tests.test_skill_activation import make_service as explicit_service, write_skill
from tests.test_skill_selection import Recorder, make_service as automatic_service


windows = pytest.mark.skipif(os.name != "nt", reason="Native Windows skill catalog")
LOGGER = "app.runtime.skills.diagnostics"
PRIVATE = "PRIVATE-PROMPT-AND-BODY-6-1"


def events(caplog):
    return [json.loads(record.getMessage().removeprefix("[skill] "))
            for record in caplog.records if record.name == LOGGER]


@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
def test_allowlist_excludes_raw_content_metadata_paths_and_arbitrary_labels(tmp_path, caplog, level):
    from app.runtime.skills.contracts import SkillDefinition
    skill = SkillDefinition("style\nFORGED" + "x" * 400, PRIVATE, PRIVATE,
                            tmp_path / PRIVATE, tmp_path / PRIVATE / "SKILL.md",
                            {"version": PRIVATE, "key": PRIVATE})
    with caplog.at_level(level):
        record_skill_event("activated", skill=skill, source=PRIVATE, method=PRIVATE,
                           router_result=PRIVATE, error_code=PRIVATE, location=skill.source_path)
    event = events(caplog)[0]
    assert event["body_sha256"] == sha256(PRIVATE.encode()).hexdigest()
    assert event["body_bytes"] == len(PRIVATE) and event["token_size_estimate"] == (len(PRIVATE) + 3) // 4
    assert event["token_measurement"] == "character_estimate"
    assert len(event["name"]) == 128 and event["name"].endswith("...")
    assert all(event[field] == "unknown" for field in
               ("source", "activation_method", "router_result", "error_code"))
    assert event["location_sha256"] == sha256(str(skill.source_path).encode()).hexdigest()
    assert PRIVATE not in caplog.text and str(tmp_path) not in caplog.text
    assert "\n" not in caplog.records[0].getMessage() and "\\n" in caplog.records[0].getMessage()


@windows
def test_effective_discovery_reports_project_source_hash_and_safe_load_errors(tmp_path, caplog):
    global_root, project = tmp_path / "global", tmp_path / "project"
    write_skill(global_root, "style", PRIVATE + " global")
    project_file = write_skill(project / ".orsi/skills", "style", PRIVATE + " project")
    broken = project / ".orsi/skills" / PRIVATE
    broken.mkdir()
    (broken / "SKILL.md").write_text("---\nname: broken\n---\n" + PRIVATE)
    registry = SkillRegistry(global_root=global_root, project_root=project)
    with caplog.at_level(logging.DEBUG):
        report = registry.discover()
    discovered = [event for event in events(caplog) if event["event"] == "discovered"]
    assert len(discovered) == 1 and discovered[0]["source"] == "project"
    assert discovered[0]["body_sha256"] == sha256(registry.get("style").instructions.encode()).hexdigest()
    errors = [event for event in events(caplog) if event["event"] == "load_error"]
    assert len(errors) == 1 and errors[0]["error_code"] == "missing_field"
    assert errors[0]["source"] == "project" and report.issues[0].code == "missing_field"
    assert PRIVATE not in caplog.text and str(project_file) not in caplog.text


@windows
@pytest.mark.parametrize("agent", [False, True])
def test_router_and_real_answer_injection_match_the_sent_snapshot(tmp_path, caplog, agent):
    model = Recorder(['{"skill":"design-taste-frontend"}'])
    service = automatic_service(tmp_path, model, agent=agent)
    try:
        with caplog.at_level(logging.DEBUG):
            assert service.run(PRIVATE + " request") == "reply"
        observed = events(caplog)
        assert [event["event"] for event in observed] == ["router", "injected"]
        assert observed[0]["router_result"] == "selected" and observed[0]["injected"] is False
        injected = observed[1]
        assert injected["source"] == "global" and injected["activation_method"] == "automatic"
        assert injected["injected"] is True and injected["system_message_tokens"] > 0
        sent = model.answer_requests[0][0][0]["content"]
        payload = json.loads(sent.split("\nACTIVE SKILL\n")[1].split("\nEND ACTIVE SKILL\n")[0])
        assert injected["body_sha256"] == sha256(payload["instructions"].encode()).hexdigest()
        assert len(model.router_requests) == len(model.answer_requests) == 1
        assert PRIVATE not in caplog.text and payload["instructions"] not in caplog.text
        if agent:
            assert model.answer_requests[0][1] == service.agent_runtime.registry.model_definitions()
    finally:
        service.shutdown()


@windows
@pytest.mark.parametrize("reply,reason", [
    ('{"skill":null}', "no_match"), (PRIVATE, "invalid_response"),
    (RuntimeError(PRIVATE), "model_error"),
])
def test_router_fallback_logs_only_the_result_not_response_or_exception(tmp_path, caplog, reply, reason):
    model = Recorder([reply])
    service = automatic_service(tmp_path, model)
    try:
        with caplog.at_level(logging.DEBUG):
            assert service.run(PRIVATE) == "reply"
        assert [event["event"] for event in events(caplog)] == ["router"]
        assert events(caplog)[0]["router_result"] == reason
        assert events(caplog)[0]["injected"] is False and PRIVATE not in caplog.text
    finally:
        service.shutdown()


@windows
@pytest.mark.parametrize("command", [False, True])
def test_explicit_activation_is_not_injection_and_meter_does_not_forge_injection(tmp_path, caplog, command):
    service, model = explicit_service(tmp_path, body=PRIVATE)
    try:
        with caplog.at_level(logging.DEBUG):
            if command:
                service.run("/skill style")
            else:
                service.activate_skill("style")
            service.context_budget()
        assert [event["event"] for event in events(caplog)] == ["activated"]
        assert events(caplog)[0]["activation_method"] == "explicit"
        assert events(caplog)[0]["injected"] is False and not model.requests
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            service.run(PRIVATE + " task")
            service.new_session()
        assert [event["event"] for event in events(caplog)] == ["injected", "deactivated"]
        assert events(caplog)[0]["activation_method"] == "explicit"
        assert events(caplog)[0]["body_sha256"] == sha256(PRIVATE.encode()).hexdigest()
        assert PRIVATE not in caplog.text
    finally:
        service.shutdown()


@windows
def test_explicit_rejection_never_reports_injection_or_logs_attempted_name(tmp_path, caplog):
    service, model = explicit_service(tmp_path, body=PRIVATE * 5000)
    try:
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(SkillActivationError):
                service.activate_skill(PRIVATE + " missing")
            service.activate_skill("style")
            with pytest.raises(SkillActivationError):
                service.run(PRIVATE + " task")
        assert [event["event"] for event in events(caplog)] == ["activation_error", "activated", "rejected"]
        assert events(caplog)[-1]["error_code"] == "context_limit"
        assert all(event["injected"] is False for event in events(caplog))
        assert not model.requests and PRIVATE not in caplog.text
    finally:
        service.shutdown()


@windows
def test_automatic_rejection_records_original_router_choice_and_fallback(tmp_path, caplog):
    model = Recorder(['{"skill":"design-taste-frontend"}'])
    service = automatic_service(tmp_path, model)
    path = tmp_path / "skills/design-taste-frontend/SKILL.md"
    path.write_text(path.read_text() + PRIVATE * 5000)
    service.skill_registry.reload()
    try:
        with caplog.at_level(logging.DEBUG):
            assert service.run(PRIVATE) == "reply"
        assert [event["event"] for event in events(caplog)] == ["router", "rejected"]
        assert events(caplog)[0]["router_result"] == "selected"
        assert events(caplog)[1]["router_result"] == "skill_context_limit"
        assert events(caplog)[1]["activation_method"] == "automatic"
        assert service.active_skill is None and PRIVATE not in caplog.text
    finally:
        service.shutdown()


@windows
def test_injection_hash_uses_sent_snapshot_if_catalog_changes(tmp_path, caplog):
    service, _ = explicit_service(tmp_path, body=PRIVATE)
    try:
        service.activate_skill("style")
        request = service._model_request(capability_turn=False)
        write_skill(tmp_path / "skills", "style", "replacement")
        service.skill_registry.reload()
        with caplog.at_level(logging.DEBUG):
            service._record_skill_injection(request)
        assert events(caplog)[0]["body_sha256"] == sha256(PRIVATE.encode()).hexdigest()
        assert events(caplog)[0]["source"] == "unknown"
        assert PRIVATE not in caplog.text and "replacement" not in caplog.text
    finally:
        service.shutdown()


@windows
def test_catalog_refresh_failure_logs_only_stable_code(tmp_path, caplog, monkeypatch):
    registry = SkillRegistry(global_root=tmp_path / "skills")
    def fail(**kwargs):
        raise RuntimeError(PRIVATE)
    monkeypatch.setattr("app.runtime.skills.registry.discover_skills", fail)
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        registry.reload()
    assert events(caplog) == [{"event": "catalog_error", "error_code": "refresh_failed"}]
    assert PRIVATE not in caplog.text and registry.list() == ()


@windows
def test_enabling_diagnostics_does_not_add_model_or_tokenizer_requests(tmp_path, caplog):
    class CountingRecorder(Recorder):
        def __init__(self):
            super().__init__(['{"skill":"design-taste-frontend"}'])
            self.tokenizer_requests = []

        def count_message_tokens(self, messages):
            self.tokenizer_requests.append(json.dumps(messages, sort_keys=True))
            return super().count_message_tokens(messages)

    observations = []
    for directory, level in (("silent", logging.ERROR), ("debug", logging.DEBUG)):
        model = CountingRecorder()
        service = automatic_service(tmp_path / directory, model)
        try:
            with caplog.at_level(level):
                assert service.run("Explain the frontend layout") == "reply"
            observations.append((model.tokenizer_requests, model.router_requests, model.answer_requests,
                                 service.skill_selection, model.context_length, model.max_response_tokens))
        finally:
            service.shutdown()
    assert observations[0] == observations[1]


@windows
def test_cancelled_router_logs_no_partial_response_or_reasoning(tmp_path, caplog, monkeypatch):
    from app.runtime.cancellation import TaskCancelled
    model = Recorder()
    service = automatic_service(tmp_path, model)
    def cancelled(*args, **kwargs):
        raise TaskCancelled(PRIVATE)
    monkeypatch.setattr("app.conversation.orchestrator.select_skill", cancelled)
    try:
        with caplog.at_level(logging.DEBUG):
            assert service.run(PRIVATE) == "The response was stopped."
        assert events(caplog) == [{"event": "router", "activation_method": "automatic",
                                  "router_result": "cancelled", "injected": False}]
        assert PRIVATE not in caplog.text and not model.answer_requests
    finally:
        service.shutdown()


@windows
def test_removed_active_skill_is_logged_as_missing_without_injection(tmp_path, caplog):
    service, model = explicit_service(tmp_path)
    try:
        service.activate_skill("style")
        (tmp_path / "skills/style/SKILL.md").unlink()
        service.skill_registry.reload()
        with caplog.at_level(logging.DEBUG), pytest.raises(SkillActivationError):
            service.run(PRIVATE)
        assert events(caplog) == [{"event": "activation_error", "activation_method": "explicit",
                                  "error_code": "missing_skill", "injected": False}]
        assert PRIVATE not in caplog.text and not model.requests
    finally:
        service.shutdown()


@windows
def test_persisted_debug_log_excludes_conversation_and_skill_content(tmp_path):
    from logging.handlers import RotatingFileHandler
    service, _ = explicit_service(tmp_path, body=PRIVATE)
    logger = logging.getLogger(LOGGER)
    previous_level = logger.level
    log_path = tmp_path / "orsi.log"
    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        service.activate_skill("style")
        service.run(PRIVATE + " user request")
        service.deactivate_skill()
        handler.flush()
        text = log_path.read_text(encoding="utf-8")
        recorded = [json.loads(line.removeprefix("[skill] ")) for line in text.splitlines()]
        assert [event["event"] for event in recorded] == ["activated", "injected", "deactivated"]
        assert recorded[1]["body_sha256"] == sha256(PRIVATE.encode()).hexdigest()
        assert PRIVATE not in text and str(tmp_path) not in text
        assert "reply" not in text and "Test guidance" not in text
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)
        service.shutdown()
