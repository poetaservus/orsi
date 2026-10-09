"""Coding policy reaches real requests without changing their catalog or authority."""
import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import agent_system_prompt, compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.hybrid import HybridInferenceEngine
from app.security.host_access import HostReadScope
from app.settings.agent import AgentFeatureConfig
from tests.test_personality import RequestRecorder
from tools.verify_coding_guidance import verification_disclosure


CATALOG = tuple("filesystem." + name for name in (
    "stat", "find", "list", "read_text", "search", "mkdir", "write_text", "edit_text", "copy", "move", "trash",
)) + ("application.launch",)


@pytest.mark.parametrize("answer,unrun,claimed", [
    ("I inspected source but did not run Python, imports, GUI, or tests.", True, False),
    ("Python execution: not run.\nTests: unrun.", True, False),
    ("Only source inspected; no GUI tests run.", True, False),
    ("I ran Python and all tests passed.", False, True),
    ("I executed Python and tested the GUI app.", False, True),
    ("Saved text was checked.", False, False),
    ("I didn't run tests; Tests passed.", True, True),
    ("No image generation. Python tests passed.", False, True),
    ("Originals preserved; Python and GUI checks not executed.", True, False),
])
def test_cloud_gate_distinguishes_unrun_checks_from_execution_claims(answer, unrun, claimed):
    assert verification_disclosure(answer) == (unrun, claimed)


@pytest.mark.parametrize("prompt", [agent_system_prompt, compact_agent_system_prompt])
@pytest.mark.parametrize("scope", list(HostReadScope))
def test_requested_change_set_and_copy_authority_are_consistent(prompt, scope):
    text = prompt(scope, CATALOG)
    assert "continue only while requested changes remain, then stop" in text
    assert "within the requested scope" in text
    assert "stop after a successful edit" not in text
    assert "do not call another capability unless" not in text
    assert "full replacement requires authorization from the task" in text
    assert "preserve the original" in text and "explicit destination" in text
    assert "unsolicited replacement copy" in text
    assert "completed or remaining requested work" in text
    assert "Before each edit, read the current file again" in text
    assert "Never repeat identical rejected arguments" in text
    assert "denied approval or an unknown write outcome" in text


@pytest.mark.parametrize("prompt", [agent_system_prompt, compact_agent_system_prompt])
@pytest.mark.parametrize("tool", ["filesystem.edit_text", "filesystem.write_text", "filesystem.copy"])
def test_verification_guidance_requires_actual_tool_evidence(prompt, tool):
    text = prompt(HostReadScope.PORTABLE_ROOT, ("filesystem.stat", "filesystem.read_text", tool))
    assert "Source inspection and saved-byte verification do not prove Python execution, imports, GUI behavior, or tests passed" in text
    assert "Claim a check only when an advertised tool result proves it" in text
    assert "state which checks remain unrun" in text


@pytest.mark.parametrize("prompt", [agent_system_prompt, compact_agent_system_prompt])
@pytest.mark.parametrize("catalog", [("filesystem.stat",), ("filesystem.stat", "filesystem.read_text")])
def test_read_only_catalog_does_not_receive_file_change_authority(prompt, catalog):
    text = prompt(HostReadScope.PORTABLE_ROOT, catalog)
    assert "continue only while requested changes remain" not in text
    assert "full replacement requires authorization" not in text
    assert "filesystem.edit_text" not in text and "filesystem.write_text" not in text


@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_service_request_keeps_whole_catalog_user_text_and_scoped_completion(tmp_path, mode):
    backend = RequestRecorder(16384)
    inference = HybridInferenceEngine(local=backend if mode == "local" else None,
        cloud=backend if mode == "cloud" else None, default_mode=mode, fallback_to_local=False)
    flags = AgentFeatureConfig(**{f"filesystem_{name}_enabled": True for name in (
        "stat", "find", "list", "read_text", "search", "mkdir", "write_text", "edit_text", "copy", "move", "trash",
    )}, application_launch_enabled=True)
    runtime = build_agent_runtime(inference, config=flags, portable_root=tmp_path,
        state_directory=tmp_path / "state")
    service = ConversationService(inference, ConversationStore(tmp_path / "chat.json"),
        agent_runtime=runtime, portable_root=tmp_path)
    request = 'Fix the requested bugs in main.py and helpers.py; preserve unrelated source.'
    try:
        service.run(request)
        messages, names = backend.requests[-1]
        assert set(names) == set(CATALOG) and names == runtime.registry.model_visible_names
        assert messages[-1] == {"role": "user", "content": request}
        core = messages[0]["content"]
        assert "continue only while requested changes remain, then stop" in core
        assert "external approval" in core and "untrusted data" in core
        assert "checks remain unrun" in core
        assert "batch up to" in core if mode == "cloud" else "Normally make one tool call at a time" in core
        assert len(core.encode()) < len(agent_system_prompt(HostReadScope.PORTABLE_ROOT, names).encode()) / 2
        assert service._turn_result.capability_calls == 0
        assert list(tmp_path.glob("*.py")) == []
    finally:
        service.shutdown()
