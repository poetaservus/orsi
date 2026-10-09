"""The actual Python package retains host authority, lazy reads and explicit scope."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelResponse
from app.runtime.skills import SkillInstaller, SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.settings.agent import load_agent_feature_config
from tests.test_skill_activation import skill_payload
from tests.test_skill_reference_conversations_v1 import PackageModel, reader_pairs, request_reference


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows skill package access")
PACKAGE = Path(__file__).resolve().parents[1] / "skills/python-coder"


class HostModel(PackageModel):
    # Isolate package wiring from the small generic scripted adapter's context.
    context_length = 131072
    max_response_tokens = 1024


@pytest.fixture
def host(tmp_path):
    registry = SkillRegistry(global_root=tmp_path / "skills")
    installer = SkillInstaller(registry)
    installer.install(PACKAGE)
    portable = tmp_path / "portable"
    portable.mkdir()
    model = HostModel()
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=load_agent_feature_config(),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(model, ConversationStore(portable / "chat.json"),
        agent_runtime=runtime, portable_root=portable, skill_registry=registry,
        automatic_skills_enabled=False, host_access_policy=policy, allowed_read_roots=(portable,))
    try:
        yield service, model, installer.info("python-coder")
    finally:
        service.shutdown()


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("scope", ["message", "session"])
def test_actual_package_reads_one_reference_without_changing_host_authority(host, mode, scope):
    service, model, skill = host
    model.mode = mode
    model.actions = iter([request_reference("references/40-testing.md"),
        ModelResponse.text("Source inspection only; Python and GUI checks were not run.")])
    runtime = service.agent_runtime
    definitions = runtime.registry.model_definitions()
    gate, limits = runtime.permission_gate, runtime.limits
    if scope == "session":
        service.activate_skill("python-coder")
    kwargs = {"skill_name": "python-coder"} if scope == "message" else {}
    request = "Inspect the verification guidance for this Python bug."
    assert service.image_route_decision(request, **kwargs).route == "agent"
    service.run(request, **kwargs)
    first, tools = model.requests[0]
    payload = skill_payload(first)
    core = compact_agent_system_prompt(service.host_read_scope, tuple(d.name for d in tools),
        str(service.host_access_policy.user_home), allow_read_batches=mode == "cloud")
    assert first[0]["content"].startswith(core)
    assert payload["instructions"] == skill.instructions
    assert set(payload["references"]["paths"]) == {
        p.relative_to(PACKAGE).as_posix() for p in (PACKAGE / "references").glob("*.md")}
    assert len(payload["references"]["paths"]) == 12
    for reference in (PACKAGE / "references").glob("*.md"):
        assert reference.read_text(encoding="utf-8") not in first[0]["content"]
    assert {d.name for d in tools} == {d.name for d in definitions} | {"skill.read_reference"}
    returned = reader_pairs(model.requests[1][0])[-1]["result"]
    assert returned["success"] and returned["output"]["has_more"]
    assert not returned["output"]["complete_document"]
    raw = (skill.root_path / "references/40-testing.md").read_bytes()
    assert returned["output"]["text"] == raw[:returned["output"]["end_offset"]].decode("utf-8")
    calls = service.store.turns()[-1].settled_calls
    assert len(calls) == 1 and calls[0].call.capability == "skill.read_reference"
    assert runtime.registry.model_definitions() == definitions
    assert runtime.permission_gate is gate and runtime.limits is limits
    assert (service.active_skill is not None) == (scope == "session")
    service.run("Explain the reported verification limit.")
    assert ("\nACTIVE SKILL\n" in model.requests[-1][0][0]["content"]) == (scope == "session")
    assert not service.store.turns()[-1].settled_calls


@pytest.mark.parametrize("session", [False, True])
def test_actual_package_picker_clears_message_selection_and_preserves_session_choice(host, session):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    from tests.test_skill_picker_ui import wait_finished

    app = QApplication.instance() or QApplication([])
    service, model, _ = host
    if session:
        service.activate_skill("python-coder")
    ui = MainWindow(service, "TEST")
    ui.show()
    app.processEvents()
    try:
        ui.input.setFocus()
        QTest.keyClicks(ui.input, "/skill python")
        QTest.keyClick(ui.input, Qt.Key.Key_Return)
        assert ui.skill_picker.selected_name == "python-coder"
        ui.input.setPlainText("Inspect the Python verification boundary.")
        ui.send.click()
        assert ui.skill_picker.selected_name is None and ui.skill_picker.chip.isHidden()
        wait_finished(ui)
        assert skill_payload(model.requests[-1][0])["name"] == "python-coder"
        assert (service.active_skill is not None) == session
        ui.input.setPlainText("Explain the reported verification limit.")
        ui.send.click()
        wait_finished(ui)
        assert ("\nACTIVE SKILL\n" in model.requests[-1][0][0]["content"]) == session
    finally:
        wait_finished(ui)
        ui.close()
