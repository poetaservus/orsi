from dataclasses import replace
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
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


@pytest.mark.parametrize("windowless", [False, True])
@pytest.mark.parametrize("broken", [False, True])
def test_real_browser_inspection_catches_references_scroll_and_interactions(tmp_path, broken, windowless, monkeypatch):
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
    if windowless:
        # ORSI.cmd launches pythonw; console-only tests missed its child-worker behavior.
        monkeypatch.setattr("app.capabilities.project_verification.sys",
            SimpleNamespace(executable=str(Path(sys.executable).with_name("pythonw.exe"))))
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": str(Path(sys.executable).resolve()), "server_arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
        "steps": [{"action": "fill", "target": "#field", "value": "test"}, {"action": "click", "target": "#button"},
            {"action": "text", "target": "#result", "value": "clicked"}, {"action": "scroll", "target": "#scroll"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success, result.error
    output = result.output
    assert output.get("inspection_complete"), output
    assert output["passed"] is not broken
    assert output["verification_status"] == ("failed" if broken else "passed")
    assert (output["retry_guidance"] is not None) is broken
    assert output["checks"][2]["passed"]
    assert Path(output["screenshot_path"]).is_file()
    if broken:
        assert "read-only test/report request" in output["retry_guidance"]
        assert any(item["kind"] == "http_error" for item in output["problems"])
        assert output["layout"]["missingFragments"] == ["#missing"]
        assert not output["checks"][-1]["passed"]  # Real wheel scrolling catches overflow:hidden.
    try:
        psutil.Process(output["preview_pid"]).wait(timeout=1)
    except psutil.NoSuchProcess:
        pass


def test_browser_captures_the_final_section_after_navigating_from_intro(tmp_path):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    (tmp_path / "index.html").write_text(
        '<style>body{margin:0}section{height:100vh}</style>'
        '<section id="intro">Intro</section><section id="affected">Affected model section</section>', encoding="utf-8")
    port = free_port()
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": str(Path(sys.executable).resolve()),
        "server_arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
        "steps": [{"action": "in_view", "target": "#intro"},
            {"action": "scroll", "amount": 800}, {"action": "in_view", "target": "#affected"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and result.output["passed"], result
    assert [target["target"] for target in result.output["capture_targets"]] == ["#affected"]
    assert result.output["capture_targets"][0]["in_viewport"]
    assert result.output["layout"]["scrollTop"] == 800 and result.output["owned_processes_released"]


def test_browser_waits_for_slow_preview_without_corrupting_observations(tmp_path):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    (tmp_path / "index.html").write_text("<h1>Ready preview</h1>", encoding="utf-8")
    port = free_port()
    code = ("import time,runpy,sys; time.sleep(1.5); "
        f"sys.argv=['http.server','{port}','--bind','127.0.0.1']; "
        "runpy.run_module('http.server',run_name='__main__')")
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": str(Path(sys.executable).resolve()), "server_arguments": ["-c", code],
        "steps": [{"action": "text", "target": "h1", "value": "Ready preview"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success, result.error
    assert result.output.get("inspection_complete"), result.output
    assert result.output["passed"], result.output
    assert result.output["owned_processes_released"]
    try:
        psutil.Process(result.output["preview_pid"]).wait(timeout=1)
    except psutil.NoSuchProcess:
        pass


def test_missing_preview_returns_owned_server_recovery_then_corrected_call_passes(tmp_path):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    (tmp_path / "index.html").write_text("<h1>Recovered preview</h1>", encoding="utf-8")
    port = free_port()
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "steps": [{"action": "text", "target": "h1", "value": "Recovered preview"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and result.output["owned_processes_released"]
    assert not result.output["passed"] and not result.output["inspection_complete"]
    assert result.output["verification_status"] == "unavailable"
    assert result.output["failure_kind"] == "preview_navigation_failed"
    assert result.output["preview_server_started"] is False
    recovery = result.output["recovery"]
    assert recovery["capability"] == "project.inspect"
    assert recovery["required_if_preview_not_running"] == ["server_executable", "server_arguments"]
    assert "shell.run stops its child processes" in recovery["instruction"]
    corrected = args | {"server_executable": str(Path(sys.executable).resolve()),
        "server_arguments": ["-m", "http.server", str(port), "--bind", "127.0.0.1"]}
    # Recovery supplies guidance, never authority for the corrected executable.
    assert not tool.invoke(corrected, approved(tool, args, context(tmp_path))).success
    result = tool.invoke(corrected, approved(tool, corrected, context(tmp_path)))
    assert result.success and result.output["inspection_complete"] and result.output["passed"]
    assert result.output["owned_processes_released"]
    try:
        psutil.Process(result.output["preview_pid"]).wait(timeout=1)
    except psutil.NoSuchProcess:
        pass


@pytest.mark.parametrize("mode", ["websocket", "slow_asset", "failed_asset", "blocked_origin", "blocked_socket"])
def test_browser_handles_development_resources_and_preserves_real_failures(tmp_path, mode):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    port, other_port = free_port(), free_port()
    script = tmp_path / "preview.py"
    script.write_text('''import base64,hashlib,sys,time
from pathlib import Path
from threading import Thread
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
mode=sys.argv[2]
other_port=int(sys.argv[3])
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  if self.server.server_port == other_port:
   Path('escaped').write_text('Unexpected off-origin request')
  if self.path == '/redirect.png':
   self.send_response(302); self.send_header('Location',f'http://127.0.0.1:{other_port}/forbidden')
   self.end_headers(); return
  if self.path == '/socket':
   key=self.headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
   self.send_response(101); self.send_header('Upgrade','websocket'); self.send_header('Connection','Upgrade')
   self.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1(key.encode()).digest()).decode())
   self.end_headers(); self.wfile.write(b'\\x81\\x02ok'); self.wfile.flush(); time.sleep(1); return
  if self.path == '/missing.png':
   self.close_connection=True; return
  if self.path == '/app.js':
   time.sleep(2.5)
   body=b"setTimeout(()=>{document.querySelector('#root').innerHTML='<p id=ready>Ready</p>'},150)"
   content_type='text/javascript'
  else:
   content_type='text/html'
   if mode == 'websocket':
    body=b"<div id=root></div><script>const ws=new WebSocket('ws://'+location.host+'/socket'); ws.onmessage=()=>document.querySelector('#root').innerHTML='<p id=ready>Ready</p>'</script>"
   elif mode == 'slow_asset':
    body=b"<div id=root></div><script type=module src=/app.js></script>"
   elif mode == 'blocked_origin':
    body=(f"<p id=ready>Ready</p><img src=/redirect.png><img src=http://127.0.0.1:{other_port}/forbidden>").encode()
   elif mode == 'blocked_socket':
    body=(f"<p id=ready>Ready</p><script>new WebSocket('ws://127.0.0.1:{other_port}/socket')</script>").encode()
   else:
    body=b"<p id=ready>Ready</p><img src=/missing.png>"
  self.send_response(200); self.send_header('Content-Type',content_type)
  self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
other=ThreadingHTTPServer(('127.0.0.1',other_port),Handler)
Thread(target=other.serve_forever,daemon=True).start()
ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
''', encoding="utf-8")
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": str(Path(sys.executable).resolve()), "server_arguments": [str(script), str(port), mode, str(other_port)],
        "steps": [{"action": "visible", "target": "#ready"}, {"action": "text", "target": "#ready", "value": "Ready"}]}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success, result.error
    assert result.output.get("inspection_complete"), result.output
    assert result.output["passed"] is (mode not in {"failed_asset", "blocked_origin", "blocked_socket"}), result.output
    assert all(check["passed"] for check in result.output["checks"]), result.output
    if mode == "failed_asset":
        assert any(item["kind"] == "failed_reference" for item in result.output["problems"])
    if mode == "blocked_origin":
        assert {"blocked_reference", "blocked_redirect"}.issubset(item["kind"] for item in result.output["problems"])
        assert not (tmp_path / "escaped").exists()
    if mode == "blocked_socket":
        assert any(item["kind"] == "blocked_reference" for item in result.output["problems"])
        assert not (tmp_path / "escaped").exists()


def test_inspection_deadline_releases_a_preview_that_never_becomes_ready(tmp_path):
    pytest.importorskip("playwright")
    state = Path(__file__).resolve().parents[1] / "state"
    if not (state / "playwright").is_dir():
        pytest.skip("Local Playwright browser is not installed.")
    port = free_port()
    tool = ProjectInspectCapability(state)
    args = {"project_path": str(tmp_path), "kind": "browser", "url": f"http://127.0.0.1:{port}/",
        "server_executable": str(Path(sys.executable).resolve()),
        "server_arguments": ["-c", "import os,time; from pathlib import Path; Path('preview.pid').write_text(str(os.getpid())); time.sleep(60)"],
        "timeout_seconds": 2}
    result = tool.invoke(args, approved(tool, args, context(tmp_path)))
    assert result.success and not result.output["passed"]
    assert not result.output["inspection_complete"] and result.output["stop_reason"] == "timeout"
    assert result.output["owned_processes_released"]
    try:
        psutil.Process(int((tmp_path / "preview.pid").read_text())).wait(timeout=1)
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
