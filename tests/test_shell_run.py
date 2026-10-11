"""Real shell execution, authority, command transport and bounded cleanup."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from threading import Thread
from time import monotonic, sleep

import psutil
import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunResult, AgentRunStatus, SettledCall
from app.agent.progress import recovery_stop_progress
from app.agent.goals import ArtifactEvidence, TaskGoal, VerificationEvidence, observe_goal
from app.capabilities.catalog import build_builtin_registry
from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityExecutionError, CapabilityResult, PermissionClass
from app.capabilities.shell_run import ShellRunArguments, ShellRunCapability, shell_command, shell_executable
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import agent_system_prompt, compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.activity import capability_activity
from app.runtime.cancellation import CancellationSource
from app.security.default_permissions import build_default_permission_gate
from app.security.host_access import HostAccessPolicy, HostReadScope
from app.security.permissions import ApprovalStatus, PermissionDecision, prepare_capability_call
from app.settings.agent import AgentFeatureConfig, load_agent_feature_config
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call
from tests.test_filesystem_read_text import context
from tests.test_project_verification import approved


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows shell and owned process integration")


def arguments(folder, program, **overrides):
    return {"workdir": str(folder), "command": program, **overrides}


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def invoke(folder, command, **overrides):
    tool = ShellRunCapability()
    args = arguments(folder, command, **overrides)
    result = tool.invoke(args, approved(tool, args, context(folder)))
    assert result.success, result.error
    return result.output


def test_gate_config_catalog_and_command_preview(tmp_path, monkeypatch):
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, shell_run_enabled=True)
    catalog = build_builtin_registry(flags, application_root=tmp_path, state_directory=tmp_path)
    tool = catalog.resolve("shell.run")
    args = arguments(tmp_path, "Get-ChildItem | Select-Object -First 1", timeout_seconds=17)
    prepared = prepare_capability_call(tool, args, context(tmp_path))
    gate = build_default_permission_gate(flags, HostAccessPolicy.portable_root(tmp_path), (tmp_path,))
    assert gate.evaluate(prepared).decision == PermissionDecision.ASK
    assert prepared.request.permission == PermissionClass.EXECUTE
    preview = prepared.request.approval_preview
    assert args["command"] in preview and str(tmp_path).replace("\\", "\\\\") in preview
    assert '"timeout_seconds": 17' in preview and "not a sandbox" in preview
    assert not tool.invoke(args, context(tmp_path)).success
    assert "shell.run" not in build_builtin_registry(AgentFeatureConfig(), application_root=tmp_path, state_directory=tmp_path).names
    with pytest.raises(ValueError):
        AgentFeatureConfig(shell_run_enabled=True)
    monkeypatch.setenv("ORSI_ENABLE_SHELL_RUN", "false")
    assert not load_agent_feature_config().shell_run_enabled
    monkeypatch.setenv("ORSI_ENABLE_SHELL_RUN", "true")
    assert load_agent_feature_config().shell_run_enabled


@pytest.mark.parametrize("prompt", [agent_system_prompt, compact_agent_system_prompt])
def test_both_model_catalogs_advertise_shell_without_denying_it(prompt):
    text = prompt(HostReadScope.PORTABLE_ROOT, capability_names=("filesystem.stat", "shell.run"))
    assert "shell.run" in text
    if prompt is agent_system_prompt:
        assert "They cannot run arbitrary processes" not in text and "use the shell" not in text
        assert "two read-only capabilities" not in text
        assert "not an OS sandbox" in text and "They cannot" not in text


@pytest.mark.parametrize("changes", [{"timeout_seconds": 301}, {"timeout_seconds": 0}, {"command": "x" * 8001},
    {"command": "😀" * 4001}, {"command": "\0"}, {"command": "   "}, {"shell": "bash"},
    {"shell": "cmd", "command": "echo one\necho two"}, {"env": {"KEY": "value"}}])
def test_invalid_commands_fail_before_approval(tmp_path, changes):
    with pytest.raises(ValueError):
        ShellRunArguments.model_validate(arguments(tmp_path, "echo ok", **changes))


@pytest.mark.parametrize("path", ["relative", "missing", "root", "outside"])
def test_workdir_is_absolute_existing_and_in_read_scope(tmp_path, path):
    value = {"relative": ".", "missing": str(tmp_path / "missing"),
        "root": tmp_path.anchor, "outside": str(tmp_path.parent)}[path]
    with pytest.raises(CapabilityExecutionError):
        prepare_capability_call(ShellRunCapability(), arguments(value, "echo ok"), context(tmp_path))


@pytest.mark.parametrize("changes", [{"command": "'changed'"}, {"shell": "cmd"}, {"timeout_seconds": 10}, {"workdir": "child"}])
def test_approval_cannot_authorize_changed_command_shell_deadline_or_directory(tmp_path, changes):
    tool = ShellRunCapability()
    (tmp_path / "child").mkdir()
    args = arguments(tmp_path, "'approved'")
    ctx = approved(tool, args, context(tmp_path))
    if "workdir" in changes:
        changes = {"workdir": str(tmp_path / changes["workdir"])}
    result = tool.invoke(args | changes, ctx)
    assert not result.success and result.error.code == Code.PERMISSION_DENIED


def test_approval_binds_shell_file_and_directory_identity_not_directory_timestamp(tmp_path, monkeypatch):
    tool = ShellRunCapability()
    args = arguments(tmp_path, "'ok'")
    ctx = approved(tool, args, context(tmp_path))
    (tmp_path / "new-output").write_text("not an identity change")
    assert tool.permission_resource_identity(tool.validate_arguments(args), ctx) == ctx.authorized_resource_identity
    real = shell_executable("powershell")
    monkeypatch.setattr("app.capabilities.shell_run._file_identity", lambda path: (str(real), "replaced"))
    assert tool.invoke(args, ctx).error.code == Code.PERMISSION_DENIED


def test_replacing_working_directory_invalidates_approval(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    tool = ShellRunCapability()
    args = arguments(folder, "'must not execute'")
    ctx = approved(tool, args, context(tmp_path))
    folder.rename(tmp_path / "previous-project")
    folder.mkdir()
    assert tool.invoke(args, ctx).error.code == Code.PERMISSION_DENIED


def test_actual_powershell_script_pipeline_unicode_cwd_and_stderr(tmp_path):
    folder = tmp_path / "space & (quotes) ' unicode ő"
    folder.mkdir()
    output = invoke(folder, "$value = 'árvíz $HOME `tick (x)'\n$value | ForEach-Object { $_ + ' ok' }\n"
        "[Console]::Error.WriteLine('err-ő')\n(Get-Location).Path")
    assert "árvíz $HOME `tick (x) ok" in output["output"]
    assert "err-ő" in output["output"] and str(folder) in output["output"]
    assert output["exit_code"] == 0 and output["command_completed"] and output["owned_processes_released"]
    assert output["command_succeeded"]
    assert output["content_is_untrusted"]


@pytest.mark.parametrize("command,code", [("throw 'expected failure'", 1),
    ("Write-Error 'expected failure'", 1), ("Get-Item 'missing-file'", 1), ("exit 7", 7),
    ("& PYTHON -c 'import sys; sys.exit(9)'", 9)])
def test_powershell_errors_and_native_exit_codes_are_not_success(tmp_path, command, code):
    command = command.replace("PYTHON", ps_quote(Path(sys.executable).resolve()))
    output = invoke(tmp_path, command)
    assert output["exit_code"] == code and output["command_completed"]
    assert not output["command_succeeded"]


def test_cmd_quotes_batch_redirection_and_native_exit_code(tmp_path):
    batch = tmp_path / "project tool & (test).cmd"
    batch.write_text('@echo off\r\necho batch-working\r\nexit /b 9\r\n', encoding="ascii")
    output = invoke(tmp_path, f'echo "space & literal" > "out (test).txt" & call "{batch}"', shell="cmd")
    assert output["exit_code"] == 9
    assert "batch-working" in output["output"]
    assert (tmp_path / "out (test).txt").read_text().strip() == '"space & literal"'


@pytest.mark.parametrize("shell", ["powershell", "cmd"])
def test_native_stdout_stderr_and_unicode_are_text_without_corrupting_exit_status(tmp_path, shell):
    script = tmp_path / "output.py"
    script.write_text("import sys; print('árvíz-ő'); print('diagnostic-ő', file=sys.stderr)", encoding="utf-8")
    exe = Path(sys.executable).resolve()
    command = f"& {ps_quote(exe)} {ps_quote(script)}" if shell == "powershell" else f'"{exe}" "{script}"'
    output = invoke(tmp_path, command, shell=shell)
    assert output["exit_code"] == 0
    assert "árvíz-ő" in output["output"] and "diagnostic-ő" in output["output"]
    assert "CLIXML" not in output["output"]


@pytest.mark.parametrize("shell", ["powershell", "cmd"])
def test_shell_can_invoke_installed_tool_and_read_only_receives_filtered_environment(tmp_path, monkeypatch, shell):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-inherited")
    monkeypatch.setenv("ORSI_UNTRUSTED_HOOK", "must-not-be-inherited")
    script = tmp_path / "environment.py"
    script.write_text("import os,sys,json; print(json.dumps([os.getcwd(),os.getenv('OPENAI_API_KEY'),"
        "os.getenv('ORSI_UNTRUSTED_HOOK'),sys.stdin.read()]))", encoding="utf-8")
    exe = str(Path(sys.executable).resolve())
    command = f"& {ps_quote(exe)} {ps_quote(script)}" if shell == "powershell" else f'"{exe}" "{script}"'
    output = invoke(tmp_path, command, shell=shell)
    assert output["exit_code"] == 0
    assert json.loads(output["output"].strip()) == [str(tmp_path), None, None, ""]
    if shell == "powershell":
        argv, raw = shell_command(ShellRunArguments.model_validate(arguments(tmp_path, command)), shell_executable(shell))
        assert "-NoProfile" in argv and "-NonInteractive" in argv and raw is None


@pytest.mark.parametrize("limit", ["timeout", "output", "cancel", "normal_exit"])
def test_shell_stops_owned_descendants_and_preserves_unrelated_processes(tmp_path, limit):
    script = tmp_path / "worker.py"
    report = tmp_path / "pids.json"
    script.write_text("import json,os,pathlib,subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
        "pathlib.Path('pids.json').write_text(json.dumps([os.getpid(),child.pid]))\n"
        + ("print('x'*100000,flush=True);time.sleep(60)" if limit == "output" else
            "pass" if limit == "normal_exit" else "time.sleep(60)"), encoding="utf-8")
    source = CancellationSource()
    command = f"& {ps_quote(Path(sys.executable).resolve())} {ps_quote(script)}"
    args = arguments(tmp_path, command, timeout_seconds=3 if limit == "timeout" else 10)
    tool = ShellRunCapability()
    ctx = approved(tool, args, context(tmp_path, cancellation=source.token))
    from app.runtime.owned_process import start_owned_process
    unrelated = start_owned_process([sys.executable, "-c", "import time;time.sleep(60)"], cwd=tmp_path, env=os.environ.copy())
    def cancel_when_running():
        deadline = monotonic() + 8
        while not report.exists() and monotonic() < deadline:
            sleep(0.01)
        source.cancel("cancel shell")
    timer = Thread(target=cancel_when_running) if limit == "cancel" else None
    if timer:
        timer.start()
    try:
        result = tool.invoke(args, ctx)
        assert report.is_file()
        for pid in json.loads(report.read_text()):
            assert not psutil.pid_exists(pid)
        assert unrelated.poll() is None
        if limit == "cancel":
            assert not result.success and result.error.code == Code.CANCELLED
        else:
            assert result.success and result.output["owned_processes_released"]
            assert result.output["stop_reason"] == {"timeout": "timeout", "output": "output_limit", "normal_exit": None}[limit]
            assert result.output["command_completed"] is (limit == "normal_exit")
            assert len(result.output["output"].encode()) <= 64 * 1024
    finally:
        unrelated.close()
        if timer:
            timer.join(9)


def test_serialized_output_keeps_status_inside_executor_envelope(tmp_path):
    output = invoke(tmp_path, "[Console]::Write(([char]1).ToString() * 60000)")
    assert len(json.dumps(output).encode()) < 64 * 1024
    assert output["output_truncated"] and output["owned_processes_released"]
    assert output["exit_code"] == 0 and output["stop_reason"] is None


@pytest.mark.parametrize("mode", ["approve", "deny", "automatic"])
def test_real_shell_through_conversation_approval_execution_and_durable_recall(tmp_path, mode):
    approve = mode != "deny"
    model = RoomyScriptedModel([call(1, "shell.run", **arguments(tmp_path,
        "'written' | Set-Content -LiteralPath 'shell-output.txt'; 'command finished'")),
        ModelResponse.text("The approved command finished." if approve else "The command was declined and did not run.")])
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True, shell_run_enabled=True),
        portable_root=tmp_path, state_directory=tmp_path / "state")
    runtime.set_tool_approval_required(mode != "automatic")
    store = ConversationStore(tmp_path / "conversation.json")
    service = ConversationService(model, store, agent_runtime=runtime, portable_root=tmp_path)
    reviews = []
    def review(record):
        reviews.append(record)
        service.resolve_approval(record.approval_id, approve)
    service.set_approval_requester(review)
    try:
        service.run("Run the command in this project.")
        assert len(reviews) == (0 if mode == "automatic" else 1)
        assert all(record.capability == "shell.run" for record in reviews)
        assert (tmp_path / "shell-output.txt").exists() is approve
        records = runtime.approval_manager.records
        assert records[0].status == (ApprovalStatus.CONSUMED if approve else ApprovalStatus.DENIED)
        restored = ConversationStore(store.path)
        assert restored.turns()[-1] == store.turns()[-1]
        assert not restored.turns()[-1].goal.verification  # A command is not a build/test receipt.
        assert capability_activity("shell.run", {"command": "PRIVATE CONTENT"}) == "Running a command…"
    finally:
        service.shutdown()


@pytest.mark.parametrize("error", [None, Code.CANCELLED, Code.TIMED_OUT, Code.OUTCOME_UNKNOWN, Code.PERMISSION_DENIED])
def test_shell_invalidates_prior_checks_even_outside_workdir_without_claiming_test_success(error):
    goal = TaskGoal(goal_id="turn-1", objective="Fix and verify",
        artifacts=(ArtifactEvidence(path="C:/other/file.py", saved_sha256="a" * 64,
            mutation_call_id="save", source_check_call_id="read"),),
        verification=(VerificationEvidence(call_id="test", project_path="C:/other", kind="test", passed=True),))
    result = CapabilityResult(call_id="shell", capability="shell.run", success=error is None,
        output={"exit_code": 0} if error is None else None,
        error={"code": error, "message": "interrupted"} if error else None, duration_ms=1)
    settled = SettledCall(provider_message_id="message",
        call=ModelCapabilityCall(provider_call_id="shell", capability="shell.run", arguments=arguments("C:/work", "command")), result=result)
    after = observe_goal(goal, settled)
    if error == Code.PERMISSION_DENIED:
        assert after == goal
    else:
        assert after.verification[0].stale and after.artifacts[0].integrity_uncertain
        assert after.artifacts[0].source_check_call_id is None and len(after.verification) == 1
    stopped = AgentRunResult(status=AgentRunStatus.REPEATED_CALL, message="Repeated tool call.",
        steps=1, capability_calls=1, protocol_failures=0, settled_calls=(settled,))
    report = recovery_stop_progress(stopped)
    assert "Shell commands do not enumerate file changes" in report
    assert "No successful file changes" not in report
