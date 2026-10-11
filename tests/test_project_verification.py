from dataclasses import replace
import json
from pathlib import Path
import socket
import subprocess
import sys
from threading import Timer
from time import monotonic, sleep

import psutil
import pytest

from app.capabilities.project_verification import (ProjectVerifyCapability, ProjectInspectCapability,
    ProjectVerificationArguments, ProjectInspectionArguments, worker_environment)
from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError, PermissionClass
from app.capabilities.catalog import build_builtin_registry
from app.runtime.cancellation import CancellationSource
from app.runtime.owned_process import start_owned_process
from app.security.default_permissions import build_default_permission_gate
from app.security.host_access import HostAccessPolicy
from app.security.permissions import prepare_capability_call, PermissionDecision
from app.settings.agent import AgentFeatureConfig
from tests.test_filesystem_read_text import context


def approved(tool, arguments, ctx):
    parsed = tool.validate_arguments(arguments)
    return replace(ctx, authorized_resource=str(tool.permission_resource(parsed, ctx)),
        authorized_resource_identity=tool.permission_resource_identity(parsed, ctx))


def command(project, code, **overrides):
    return {"project_path": str(project), "kind": "test", "executable": str(Path(sys.executable).resolve()),
        "arguments": ["-c", code], **overrides}


def test_catalog_gates_and_exact_command_approval(tmp_path):
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, project_verify_enabled=True, project_inspect_enabled=True)
    registry = build_builtin_registry(flags, application_root=tmp_path, state_directory=tmp_path / "state")
    policy = HostAccessPolicy.portable_root(tmp_path)
    gate = build_default_permission_gate(flags, policy, (tmp_path,))
    tool = registry.resolve("project.verify")
    prepared = prepare_capability_call(tool, command(tmp_path, "print('build')"), context(tmp_path))
    assert gate.evaluate(prepared).decision == PermissionDecision.ASK
    assert prepared.request.permission == PermissionClass.EXECUTE
    assert "print('build')" in prepared.request.approval_preview
    assert not tool.invoke(command(tmp_path, "raise Exception()"), context(tmp_path)).success
    assert "project.verify" not in build_builtin_registry(AgentFeatureConfig(), application_root=tmp_path, state_directory=tmp_path).names


def test_actual_selected_command_success_failure_stderr_and_environment(tmp_path, monkeypatch):
    tool = ProjectVerifyCapability(tmp_path / "state")
    monkeypatch.setenv("OPENAI_API_KEY", "not-inherited")
    for code, passed in [("import sys; print('selected test'); print('diagnostic',file=sys.stderr)", True),
            ("import sys; print('test failed'); sys.exit(7)", False)]:
        args = command(tmp_path, code)
        result = tool.invoke(args, approved(tool, args, context(tmp_path)))
        assert result.success and result.output["passed"] is passed
        assert result.output["owned_processes_released"]
        assert result.output["output"]
        if passed:
            assert "diagnostic" in result.output["output"]
    assert "OPENAI_API_KEY" not in worker_environment()


@pytest.mark.parametrize("limit", ["timeout", "output", "cancel"])
def test_limits_release_parent_and_spawned_descendant(tmp_path, limit):
    pid_file = tmp_path / "child.pid"
    code = ("import subprocess,sys,time,pathlib; child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); "
        + ("print('x'*100000,flush=True);time.sleep(60)" if limit == "output" else "time.sleep(60)"))
    tool = ProjectVerifyCapability(tmp_path / "state")
    source = CancellationSource()
    args = command(tmp_path, code, timeout_seconds=1 if limit == "timeout" else 5)
    timer = Timer(0.5, lambda: source.cancel("test cancellation")) if limit == "cancel" else None
    if timer:
        timer.start()
    try:
        ctx = context(tmp_path, cancellation=source.token)
        result = tool.invoke(args, approved(tool, args, ctx))
        if limit == "cancel":
            assert not result.success and result.error.code == CapabilityErrorCode.CANCELLED
        else:
            assert result.success and not result.output["passed"]
            assert result.output["stop_reason"] == ("timeout" if limit == "timeout" else "output_limit")
        assert pid_file.is_file()
        assert not psutil.pid_exists(int(pid_file.read_text()))
    finally:
        if timer:
            timer.cancel()


@pytest.mark.parametrize("extra", [{"timeout_seconds": 121}, {"arguments": ["x" * 4097]}, {"kind": "shell"}])
def test_command_bounds(extra, tmp_path):
    with pytest.raises(ValueError):
        ProjectVerificationArguments.model_validate(command(tmp_path, "pass", **extra))


@pytest.mark.parametrize("filename,code", [("missing.exe", CapabilityErrorCode.NOT_FOUND), ("command.cmd", CapabilityErrorCode.INVALID_ARGUMENTS)])
def test_missing_executable_or_batch_wrapper_returns_a_correctable_failure(tmp_path, filename, code):
    tool = ProjectVerifyCapability(tmp_path / "state")
    args = command(tmp_path, "pass", executable=str(tmp_path / filename))
    with pytest.raises(CapabilityExecutionError) as caught:
        prepare_capability_call(tool, args, context(tmp_path))
    assert caught.value.code == code


@pytest.mark.parametrize("url", ["https://example.com", "http://example.com", "file:///C:/secret", "http://user:pass@localhost:8080"])
def test_browser_scope_rejects_nonlocal_targets(tmp_path, url):
    with pytest.raises(ValueError):
        ProjectInspectionArguments(project_path=str(tmp_path), kind="browser", url=url)


def free_port():
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return stream.getsockname()[1]


@pytest.mark.parametrize("broken", [False, True])
def test_real_browser_inspection_catches_references_scroll_and_interactions(tmp_path, broken):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    (tmp_path / "index.html").write_text("""<html><style>body {margin:0} #scroll {height:100px;overflow:%s} .tall {height:600px}</style>
        <input id='field'><button id='button' onclick="document.querySelector('#result').textContent='clicked'">Go</button>
        <p id='result'>ready</p><div id='scroll'><div class='tall'>long content</div></div>%s</html>"""
        % ("hidden" if broken else "auto", "<img src='/missing.png'><a href='#missing'>broken</a>" if broken else ""), encoding="utf-8")
    port = free_port()
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": str(Path(sys.executable).resolve()), "server_arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
        "steps": [{"action": "fill", "target": "#field", "value": "test"}, {"action": "click", "target": "#button"},
            {"action": "text", "target": "#result", "value": "clicked"}, {"action": "scroll", "target": "#scroll"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success, result.error
    output = result.output
    assert output.get("inspection_complete"), output
    assert output["passed"] is not broken
    assert output["checks"][2]["passed"]
    assert Path(output["screenshot_path"]).is_file()
    if broken:
        assert any(item["kind"] == "http_error" for item in output["problems"])
        assert output["layout"]["missingFragments"] == ["#missing"]
        assert not output["checks"][-1]["passed"]  # Real wheel scrolling catches overflow:hidden.
    try:
        psutil.Process(output["preview_pid"]).wait(timeout=1)
    except psutil.NoSuchProcess:
        pass


def test_real_desktop_window_inspection_and_interaction(tmp_path):
    pytest.importorskip("pywinauto")
    pytest.importorskip("PIL")
    script = tmp_path / "fixture_app.py"
    script.write_text("""from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import QTimer
app=QApplication([])
window=QWidget(); window.setWindowTitle('ORSI synthetic inspection fixture')
layout=QVBoxLayout(window); label=QLabel('Ready'); button=QPushButton('Change')
button.clicked.connect(lambda:label.setText('Changed')); layout.addWidget(label); layout.addWidget(button)
window.resize(400,240); window.show()
import ctypes
ctypes.windll.user32.ShowWindow(int(window.winId()),5); app.processEvents()
Path('ready').write_text('ready'); QTimer.singleShot(30000,app.quit); app.exec()
""", encoding="utf-8")
    process = start_owned_process([str(Path(sys.executable).resolve()), str(script)], cwd=tmp_path, env=worker_environment())
    try:
        deadline = monotonic() + 5
        while not (tmp_path / "ready").is_file() and monotonic() < deadline:
            sleep(0.01)
        assert (tmp_path / "ready").is_file()
        tool = ProjectInspectCapability(tmp_path / "state")
        args = {"project_path": str(tmp_path), "kind": "desktop", "pid": process.pid,
            "steps": [{"action": "visible"}, {"action": "click", "target": "Change"},
                {"action": "text", "target": "Changed", "value": "Changed"}]}
        result = tool.invoke(args, approved(tool, args, context(tmp_path)))
        assert result.success, result.error
        assert result.output.get("inspection_complete"), result.output.get("output", result.output)
        assert result.output["passed"], json.dumps(result.output, ensure_ascii=False)
        assert Path(result.output["screenshot_path"]).is_file()
        assert process.poll() is None  # Inspector does not own/terminate the target desktop app.
    finally:
        process.close()
