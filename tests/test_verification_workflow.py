from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import SettledCall
from app.agent.goals import TaskGoal, observe_goal, verification_report
from app.capabilities.contracts import CapabilityResult
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore, TurnHistoryError
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.settings.agent import AgentFeatureConfig
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call


def test_real_project_build_selected_test_then_browser_inspection_are_durable(tmp_path):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    from tests.test_project_verification import free_port
    (tmp_path / "main.py").write_text("def value(): return 42\n", encoding="utf-8")
    (tmp_path / "test_project.py").write_text("import unittest\nfrom main import value\nclass TestProject(unittest.TestCase):\n def test_value(self): self.assertEqual(value(),42)\n", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html><p id='result'>Healthy preview</p></html>", encoding="utf-8")
    exe, port = str(Path(sys.executable).resolve()), free_port()
    model = RoomyScriptedModel([
        call(1, "project.verify", project_path=str(tmp_path), kind="build", executable=exe, arguments=["-m", "py_compile", "main.py"]),
        call(2, "project.verify", project_path=str(tmp_path), kind="test", executable=exe, arguments=["-m", "unittest", "discover", "-s", ".", "-p", "test_project.py"]),
        call(3, "project.inspect", project_path=str(tmp_path), kind="browser", url=f"http://127.0.0.1:{port}/",
            server_executable=exe, server_arguments=["-m", "http.server", str(port), "--bind", "127.0.0.1"],
            steps=[{"action": "text", "target": "#result", "value": "Healthy preview"}]),
        ModelResponse.text("The build, selected test and preview check passed; screenshot retained for visual review.")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        project_verify_enabled=True, project_inspect_enabled=True), portable_root=tmp_path, state_directory=tmp_path / "state")
    runtime.registry.resolve("project.inspect").state_directory = state
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(model, store, agent_runtime=runtime, portable_root=tmp_path)
    approvals = []
    def approve(record):
        approvals.append(record.capability)
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    try:
        service.run("Build this project, run its selected unit test, then inspect the local preview.")
        goal = store.turns()[-1].goal
        assert [(item.kind, item.passed, item.stale) for item in goal.verification] == [
            ("build", True, False), ("test", True, False), ("browser", True, False)]
        assert approvals == ["project.verify", "project.verify", "project.inspect"]
        assert not goal.behaviour_verified  # Scoped checks do not prove all possible behaviour.
        restored = ConversationStore(store.path)
        assert restored.turns()[-1].goal == goal
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        raw["turns"][-1]["goal"]["verification"][0]["passed"] = False
        store.path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(TurnHistoryError):
            ConversationStore(store.path)
    finally:
        service.shutdown()


def test_a_later_edit_invalidates_project_checks_and_does_not_cross_projects():
    def receipt(index, capability, arguments, output):
        return SettledCall(provider_message_id=f"scope-{index}",
            call=ModelCapabilityCall(provider_call_id=f"call-{index}", capability=capability, arguments=arguments),
            result=CapabilityResult(call_id=f"receipt-{index}", capability=capability, success=True, output=output, duration_ms=1))
    goal = TaskGoal(goal_id="turn-1", objective="Fix and verify the project")
    goal = observe_goal(goal, receipt(1, "project.verify", {"kind": "test", "project_path": "C:/project"},
        {"kind": "test", "project_path": "C:/project", "passed": True}))
    other = observe_goal(goal, receipt(2, "filesystem.write_text", {"path": "C:/project-other/main.py"},
        {"path": "C:/project-other/main.py", "sha256": "a" * 64}))
    assert not other.verification[0].stale
    changed = observe_goal(other, receipt(3, "filesystem.edit_text", {"path": "C:/project/main.py"},
        {"path": "C:/project/main.py", "sha256": "b" * 64}))
    assert changed.verification[0].stale
    assert "test stale" in verification_report(changed)
