"""An explicit message attachment cannot become a persistent session selection."""
import os

import pytest

from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.cancellation import TaskCancelled
from app.runtime.skills import SkillActivationError
from tests.test_skill_activation import Recorder, make_service, skill_payload, MALICIOUS


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows skill loading")


@pytest.mark.parametrize("agent", [False, True])
def test_message_skill_is_injected_once_and_next_message_has_no_explicit_skill(tmp_path, agent):
    service, model = make_service(tmp_path, agent=agent)
    service.automatic_skills_enabled = False
    try:
        assert service.run("First prompt", skill_name="style") == "reply"
        assert skill_payload(model.requests[-1][0])["name"] == "style"
        assert service.active_skill is None
        first_tools = model.requests[-1][1]
        assert service.store.messages()[0]["content"] == "First prompt"
        assert service.run("Next prompt") == "reply"
        assert "\nACTIVE SKILL\n" not in model.requests[-1][0][0]["content"]
        assert model.requests[-1][1] == first_tools
    finally:
        service.shutdown()


def test_temporary_attachment_restores_existing_explicit_session_selection(tmp_path):
    service, model = make_service(tmp_path)
    try:
        service.activate_skill("style")
        service.run("Message-specific prompt", skill_name="other")
        assert skill_payload(model.requests[-1][0])["name"] == "other"
        assert service.active_skill.name == "style"
        service.run("Session prompt")
        assert skill_payload(model.requests[-1][0])["name"] == "style"
    finally:
        service.shutdown()


@pytest.mark.parametrize("name", ["missing", "", False, 123])
def test_invalid_attachment_blocks_inference_and_preserves_session_selection(tmp_path, name):
    service, model = make_service(tmp_path)
    try:
        service.activate_skill("style")
        with pytest.raises(SkillActivationError):
            service.run("Do not silently route", skill_name=name)
        assert service.active_skill.name == "style" and not model.requests
        assert service.store.messages() == []
    finally:
        service.shutdown()


@pytest.mark.parametrize("failure", ["provider", "cancelled", "context"])
def test_attachment_is_cleared_on_all_terminal_paths(tmp_path, failure):
    service, model = make_service(tmp_path, body="oversized body " * 10000 if failure == "context" else "Guidance")
    service.automatic_skills_enabled = False
    try:
        if failure == "context":
            with pytest.raises(SkillActivationError):
                service.run("Prompt", skill_name="style")
            assert not model.requests
        else:
            original = model.respond
            def fail(messages):
                if failure == "cancelled":
                    raise TaskCancelled("Synthetic stop")
                raise RuntimeError("Synthetic provider failure")
            model.respond = fail
            if failure == "cancelled":
                assert service.run("Prompt", skill_name="style") == "The response was stopped."
            else:
                with pytest.raises(RuntimeError):
                    service.run("Prompt", skill_name="style")
            model.respond = original
        assert service.active_skill is None
        service.run("Follow-up")
        assert "\nACTIVE SKILL\n" not in model.requests[-1][0][0]["content"]
    finally:
        service.shutdown()


def test_message_skill_covers_tool_continuations_then_expires(tmp_path):
    model = Recorder([ModelResponse.calls((ModelCapabilityCall(provider_call_id="stat-one",
        capability="filesystem.stat", arguments={"path": "index.html"}),)), ModelResponse.text("Done")])
    service, _ = make_service(tmp_path, model=model, agent=True)
    service.automatic_skills_enabled = False
    (tmp_path / "portable/index.html").write_text("Fixture")
    try:
        assert service.run("Inspect index.html", skill_name="style") == "Done"
        assert len(model.requests) == 2
        assert all(skill_payload(messages)["name"] == "style" for messages, _ in model.requests)
        assert service._turn_result.capability_calls == 1
        assert all(record.result_success for record in service.agent_runtime.executor.journal.records)
        assert service.active_skill is None
        service.run("Thanks")
        assert "\nACTIVE SKILL\n" not in model.requests[-1][0][0]["content"]
    finally:
        service.shutdown()


def test_message_prompt_that_mentions_slash_command_is_not_session_control(tmp_path):
    service, model = make_service(tmp_path)
    try:
        service.run("/skill explain this command", skill_name="style")
        assert model.requests[-1][0][-1]["content"] == "/skill explain this command"
        assert service.active_skill is None
    finally:
        service.shutdown()


@pytest.mark.parametrize("approved", [False, True])
def test_message_skill_cannot_change_write_approval_or_tool_definitions(tmp_path, approved):
    target = tmp_path / "note.txt"
    model = Recorder([ModelResponse.calls((ModelCapabilityCall(provider_call_id="write-scoped",
        capability="filesystem.write_text", arguments={"path": str(target), "text": "Synthetic"}),)),
        ModelResponse.text("Done")])
    service, _ = make_service(tmp_path, model=model, agent=True, write=True, body=MALICIOUS)
    registry, gate = service.agent_runtime.registry, service.agent_runtime.permission_gate
    definitions = registry.model_definitions()
    approvals = []
    def decide(record):
        approvals.append(record)
        assert not target.exists()
        service.resolve_approval(record.approval_id, approved)
    service.set_approval_requester(decide)
    try:
        service.run("Write the note", skill_name="style")
        assert len(approvals) == 1 and target.exists() is approved
        assert service.agent_runtime.registry is registry and service.agent_runtime.permission_gate is gate
        assert registry.model_definitions() == definitions and service.active_skill is None
    finally:
        service.shutdown()
