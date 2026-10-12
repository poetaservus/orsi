import json
from pathlib import Path
import shutil

import psutil
import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.capabilities.project_verification import ProjectVerifyCapability, ProjectInspectCapability, project_command
from app.capabilities.contracts import CapabilityExecutionError, CapabilityErrorCode as Code
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelResponse
from app.security.host_access import HostAccessPolicy
from app.security.permissions import prepare_capability_call
from app.settings.agent import AgentFeatureConfig
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call, read, edit
from tests.test_filesystem_read_text import context
from tests.test_project_verification import approved, free_port


@pytest.fixture
def installed_npm():
    command = shutil.which("npm.cmd")
    if not command or not shutil.which("node.exe"):
        pytest.skip("Installed Windows Node/npm required")
    return command


@pytest.fixture
def fake_install(tmp_path):
    root = tmp_path / "Node installation"
    cli = root / "node_modules" / "npm" / "bin" / "npm-cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("// npm fixture", encoding="utf-8")
    wrapper = root / "npm.cmd"
    wrapper.write_text("@echo this batch must never run", encoding="utf-8")
    node = root / "node.exe"
    node.write_bytes(b"fixture identity only")
    return wrapper, node, cli


@pytest.mark.parametrize("alias", ["npm", "npm.cmd", "npm.exe", "absolute"])
def test_npm_aliases_resolve_to_approved_native_inputs(fake_install, monkeypatch, alias):
    wrapper, node, cli = fake_install
    monkeypatch.setattr(shutil, "which", lambda name: str(wrapper) if name == "npm.cmd" else str(node))
    command, inputs = project_command(str(wrapper) if alias == "absolute" else alias, ["run", "build", "--", "a b&c"])
    assert command == [str(node), str(cli), "run", "build", "--", "a b&c"]
    assert inputs == (wrapper, node, cli)


@pytest.mark.parametrize("changed", ["cli", "node", "wrapper", "path"])
def test_npm_resolution_is_bound_to_exact_approval(tmp_path, fake_install, monkeypatch, changed):
    wrapper, node, cli = fake_install
    monkeypatch.setattr(shutil, "which", lambda name: str(wrapper) if name == "npm.cmd" else str(node))
    tool = ProjectVerifyCapability(tmp_path / "state")
    args = {"project_path": str(tmp_path), "kind": "build", "executable": "npm", "arguments": ["run", "build"]}
    prepared = prepare_capability_call(tool, args, context(tmp_path))
    assert "resolved_command" in prepared.request.approval_preview
    assert str(cli).replace("\\", "\\\\") in prepared.request.approval_preview
    ctx = approved(tool, args, context(tmp_path))
    if changed == "path":
        other = tmp_path / "Other installation"
        shutil.copytree(wrapper.parent, other)
        monkeypatch.setattr(shutil, "which", lambda name: str(other / "npm.cmd"))
    else:
        target = {"cli": cli, "node": node, "wrapper": wrapper}[changed]
        target.write_bytes(target.read_bytes() + b"changed")
    monkeypatch.setattr("app.capabilities.project_verification.run_worker", lambda *a, **k: pytest.fail("Unapproved command ran"))
    result = tool.invoke(args, ctx)
    assert not result.success and result.error.code == Code.PERMISSION_DENIED


@pytest.mark.parametrize("raw", ["npm run build", "cmd.exe", "powershell.exe", "relative/npm.cmd"])
def test_invalid_commands_have_concrete_recovery_without_execution(raw):
    with pytest.raises(CapabilityExecutionError) as caught:
        project_command(raw, [])
    assert caught.value.code == Code.INVALID_ARGUMENTS
    assert "executable='npm'" in str(caught.value) and "shell.run" in str(caught.value)


def test_missing_npm_does_not_guess_or_execute(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(CapabilityExecutionError) as caught:
        project_command("npm", ["run", "build"])
    assert caught.value.code == Code.NOT_FOUND and "do not invent npm.exe" in str(caught.value)


def package_fixture(project):
    project.mkdir(exist_ok=True)
    (project / "package.json").write_text(json.dumps({"name": "orsi-command-fixture", "version": "1.0.0",
        "scripts": {"build": "node build.cjs", "preview": "node server.cjs"}}), encoding="utf-8")
    (project / "app.tsx").write_text("const animationEnabled = false;\n", encoding="utf-8")
    (project / "build.cjs").write_text("const fs=require('fs'); if(!fs.readFileSync('app.tsx','utf8').includes('animationEnabled = true')) process.exit(7); console.log('build passed');", encoding="utf-8")


@pytest.mark.parametrize("allow", [True, False])
def test_real_npm_command_honors_approval_and_records_actual_command(tmp_path, installed_npm, allow):
    package_fixture(tmp_path)
    (tmp_path / "app.tsx").write_text("const animationEnabled = true;\n", encoding="utf-8")
    tool = ProjectVerifyCapability(tmp_path / "state")
    args = {"project_path": str(tmp_path), "kind": "build", "executable": installed_npm, "arguments": ["run", "build"]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)) if allow else context(tmp_path))
    assert result.success is allow
    if allow:
        assert result.output["passed"] and "build passed" in result.output["output"]
        assert Path(result.output["command"][0]).name == "node.exe"
        assert Path(result.output["command"][1]).name == "npm-cli.js"
        assert result.output["owned_processes_released"]
    else:
        assert result.error.code == Code.PERMISSION_DENIED


def test_rejected_shell_command_recovers_edits_and_builds_in_same_turn(tmp_path, installed_npm):
    project, portable = tmp_path / "project", tmp_path / "portable"
    portable.mkdir()
    package_fixture(project)
    target = project / "app.tsx"
    model = RoomyScriptedModel([
        call(1, "project.verify", project_path=str(project), kind="build", executable="cmd.exe", arguments=["/c", "npm run build"]),
        read(2, target), edit(3, target, "animationEnabled = false", "animationEnabled = true"),
        call(4, "project.verify", project_path=str(project), kind="build", executable="npm.cmd", arguments=["run", "build"]),
        read(5, target), ModelResponse.text("Re-enabled the animation in app.tsx; the build passed.")])
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True, filesystem_edit_text_enabled=True, project_verify_enabled=True,
        full_local_read_enabled=True, context_recovery_enabled=True, conversation_context_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(model, ConversationStore(portable / "conversation.json"), agent_runtime=runtime,
        portable_root=portable, allowed_read_roots=(tmp_path,), host_access_policy=policy)
    approvals = []
    def approve(record):
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    try:
        answer = service.run("can you re-enable the animation in app.tsx")
        assert "build passed" in answer
        result = service._turn_result
        assert result.status == AgentRunStatus.COMPLETED and result.semantic_corrections == 1
        assert "animationEnabled = true" in target.read_text()
        assert [record.capability for record in approvals] == ["filesystem.edit_text", "project.verify"]
        assert all(service.approval_status(record.approval_id) == "consumed" for record in approvals)
        assert len(ConversationStore(service.store.path).turns()[-1].settled_calls) == 5
    finally:
        service.shutdown()


def test_npm_preview_resolution_stays_owned_through_browser_inspection(tmp_path, installed_npm):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser unavailable")
    package_fixture(tmp_path)
    port = free_port()
    (tmp_path / "server.cjs").write_text("require('fs').writeFileSync('preview.pid',String(process.pid)); require('http').createServer((q,r)=>r.end('<h1>Ready</h1>')).listen(Number(process.argv[2]),'127.0.0.1');", encoding="utf-8")
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": "npm", "server_arguments": ["run", "preview", "--", str(port)],
        "steps": [{"action": "text", "target": "h1", "value": "Ready"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and result.output["passed"], result
    assert result.output["owned_processes_released"]
    assert not psutil.pid_exists(int((tmp_path / "preview.pid").read_text()))
