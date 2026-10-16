"""Native persistent shell lifecycle, authority and bounded output regressions."""
import json
import os
from pathlib import Path
import sys
from threading import Thread
from time import monotonic, sleep
from urllib.request import urlopen

import psutil
import pytest

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import CapabilityErrorCode as Code
from app.capabilities.shell_run import ShellRunCapability, ShellRunArguments
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.runtime.cancellation import CancellationSource
from app.runtime.owned_process import start_owned_process
from app.settings.agent import AgentFeatureConfig
from tests.test_bounded_edit_recovery import RoomyScriptedModel, call
from tests.test_filesystem_read_text import context
from tests.test_project_verification import approved
from tests.test_shell_run import ps_quote
from app.inference.protocol import ModelResponse


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Native Windows managed shell sessions')


@pytest.fixture
def tool():
    value = ShellRunCapability()
    yield value
    value.shutdown()


def invoke(tool, root, args, ctx=None):
    ctx = ctx or context(root)
    result = tool.invoke(args, approved(tool, args, ctx))
    assert result.success, result.error
    return result.output


def launch_args(root, code, shell='powershell', **changes):
    script = root / 'server.py'
    script.write_text(code, encoding='utf-8')
    exe = Path(sys.executable).resolve()
    command = f'& {ps_quote(exe)} {ps_quote(script)}' if shell == 'powershell' else f'"{exe}" "{script}"'
    return {'command': command, 'workdir': str(root), 'shell': shell, 'background': True,
            'yield_time_ms': 1000, **changes}


SERVER = ("import http.server,json,os,pathlib,subprocess,sys\n"
    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
    "server=http.server.HTTPServer(('127.0.0.1',0),http.server.SimpleHTTPRequestHandler)\n"
    "pathlib.Path('server-info.json').write_text(json.dumps({'pids':[os.getpid(),child.pid],'port':server.server_port}))\n"
    "print('READY http://127.0.0.1:'+str(server.server_port),flush=True)\n"
    "server.serve_forever()\n")


def wait_for(predicate, timeout=6):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        value = predicate()
        if value:
            return value
        sleep(0.025)
    pytest.fail('Native session did not reach its expected state before the deadline')


def server_info(root):
    # A returned background launch is not a readiness receipt. Also avoid
    # observing the fixture's metadata between file creation and JSON completion.
    def read():
        try:
            return json.loads((root / 'server-info.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    return wait_for(read)


def session_status(tool, root, session_id, predicate):
    def read():
        value = invoke(tool, root, {'action': 'status', 'session_id': session_id})
        return value if predicate(value) else None
    return wait_for(read)


@pytest.mark.parametrize('shell', ['powershell', 'cmd'])
def test_server_survives_return_and_foreground_calls_then_stop_releases_only_owned_children(tmp_path, tool, shell):
    (tmp_path / 'index.html').write_text('synthetic preview')
    args = launch_args(tmp_path, SERVER, shell, timeout_seconds=1)
    unrelated = start_owned_process([sys.executable, '-c', 'import time;time.sleep(60)'], cwd=tmp_path, env=os.environ.copy())
    try:
        started = invoke(tool, tmp_path, args)
        assert started['running'] and started['background_processes_retained'] and not started['readiness_verified']
        assert not started['owned_processes_released'] and not started['command_completed']
        info = server_info(tmp_path)
        owned = [psutil.Process(pid) for pid in info['pids']]
        sleep(1.1)  # The ordinary command timeout must not end a persistent session.
        assert urlopen(f"http://127.0.0.1:{info['port']}/", timeout=3).read() == b'synthetic preview'
        invoke(tool, tmp_path, {'command': 'echo foreground', 'workdir': str(tmp_path), 'shell': shell})
        status = invoke(tool, tmp_path, {'action': 'status', 'session_id': started['session_id']})
        assert status['running'] and 'READY' in status['output']
        listed = invoke(tool, tmp_path, {'action': 'list'})
        assert listed['sessions'][0]['session_id'] == started['session_id']
        stopped = invoke(tool, tmp_path, {'action': 'stop', 'session_id': started['session_id']})
        assert stopped['owned_processes_released'] and not stopped['background_processes_retained']
        wait_for(lambda: all(not process.is_running() for process in owned))
        assert unrelated.poll() is None
        again = invoke(tool, tmp_path, {'action': 'stop', 'session_id': started['session_id']})
        assert again['owned_processes_released']
    finally:
        unrelated.close()


def test_app_runtime_shutdown_releases_a_settled_session(tmp_path):
    args = launch_args(tmp_path, SERVER)
    model = RoomyScriptedModel([call('start', 'shell.run', **args), ModelResponse.text('Started the managed server.')])
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, shell_run_enabled=True)
    runtime = build_agent_runtime(model, config=flags, portable_root=tmp_path, state_directory=tmp_path / 'state')
    service = ConversationService(model, ConversationStore(tmp_path / 'chat.json'), agent_runtime=runtime, portable_root=tmp_path)
    service.set_approval_requester(lambda record: service.resolve_approval(record.approval_id, True))
    try:
        assert service.run('Start the server and leave it running.') == 'Started the managed server.'
        session = service.store.turns()[0].settled_calls[0].result.output
        assert session['running'] and not service._turn_result.completion.incomplete
        info = server_info(tmp_path)
        assert urlopen(f"http://127.0.0.1:{info['port']}/", timeout=3).status == 200
    finally:
        service.shutdown()
    assert all(not psutil.pid_exists(pid) for pid in info['pids'])
    assert runtime.registry.resolve('shell.run').sessions.get(session['session_id']).snapshot()['owned_processes_released']
    service.shutdown()


def test_cancel_during_initial_observation_releases_new_session(tmp_path, tool):
    args = launch_args(tmp_path, SERVER, yield_time_ms=10000)
    source = CancellationSource()
    def cancel():
        server_info(tmp_path)
        source.cancel('Cancel initial launch')
    thread = Thread(target=cancel)
    thread.start()
    try:
        ctx = context(tmp_path, cancellation=source.token)
        result = tool.invoke(args, approved(tool, args, ctx))
        assert not result.success and result.error.code == Code.CANCELLED
        info = server_info(tmp_path)
        assert all(not psutil.pid_exists(pid) for pid in info['pids'])
        assert tool.sessions.list()['sessions'][0]['owned_processes_released']
    finally:
        thread.join(7)


def test_session_lifetime_expiry_cleans_up_without_another_tool_call(tmp_path, tool):
    # Allow native PowerShell startup to create the descendants whose expiry
    # cleanup is under test. The production lifetime policy is unchanged.
    started = invoke(tool, tmp_path, launch_args(tmp_path, SERVER, session_timeout_seconds=5, yield_time_ms=0))
    info = server_info(tmp_path)
    session = tool.sessions.get(started['session_id'])
    wait_for(lambda: session.finished)
    assert session.snapshot()['status'] == 'timed_out' and session.snapshot()['owned_processes_released']
    assert all(not psutil.pid_exists(pid) for pid in info['pids'])


def test_failed_start_returns_exit_and_output_without_claiming_readiness(tmp_path, tool):
    args = {'command': "Write-Output 'startup error'; exit 7", 'workdir': str(tmp_path), 'background': True}
    output = invoke(tool, tmp_path, args)
    output = session_status(tool, tmp_path, output['session_id'], lambda value: not value['running'])
    assert output['exit_code'] == 7 and output['status'] == 'exited'
    assert output['owned_processes_released'] and not output['readiness_verified'] and not output['command_succeeded']
    assert 'startup error' in output['output']


def test_browser_inspection_uses_session_server_without_taking_its_ownership(tmp_path, tool):
    from app.capabilities.project_verification import ProjectInspectCapability

    state = Path(__file__).resolve().parents[1] / 'state'
    if not (state / 'playwright').is_dir():
        pytest.skip('Local Playwright browser is not installed')
    (tmp_path / 'index.html').write_text('''<button id="go" onclick="document.querySelector('#result').textContent='clicked'">Go</button>
        <p id="result">ready</p><div id="scroll" style="height:100px;overflow:auto"><div style="height:1000px">long content</div></div>''')
    started = invoke(tool, tmp_path, launch_args(tmp_path, SERVER))
    info = server_info(tmp_path)
    inspection = ProjectInspectCapability(state)
    args = {'project_path': str(tmp_path), 'kind': 'browser', 'url': f"http://127.0.0.1:{info['port']}/",
            'steps': [{'action': 'click', 'target': '#go'}, {'action': 'text', 'target': '#result', 'value': 'clicked'},
                      {'action': 'scroll', 'target': '#scroll'}]}
    result = inspection.invoke(args, approved(inspection, args, context(tmp_path)))
    assert result.success and result.output['inspection_complete'] and result.output['passed'], result.output
    assert all(check['passed'] for check in result.output['checks'])
    assert tool.sessions.get(started['session_id']).snapshot()['running']
    assert urlopen(args['url'], timeout=3).status == 200


def test_rolling_output_stays_bounded_and_paged_without_stopping_server(tmp_path, tool):
    args = launch_args(tmp_path, "import time; print('x'*100000,flush=True); time.sleep(60)")
    first = invoke(tool, tmp_path, args)
    first = session_status(tool, tmp_path, first['session_id'], lambda value: value['output_total_bytes'] >= 100000)
    assert first['running'] and first['output_total_bytes'] >= 100000
    assert first['output_lost_bytes'] > 0 and first['output_has_more']
    assert len(json.dumps(first).encode()) < 64 * 1024
    second = invoke(tool, tmp_path, {'action': 'status', 'session_id': first['session_id'], 'output_offset': first['output_next_offset']})
    assert second['output_offset'] == first['output_next_offset'] and second['output_lost_bytes'] == 0
    assert second['running'] and len(second['output'].encode()) <= 8192
    invalid = {'action': 'status', 'session_id': first['session_id'], 'output_offset': 10**8}
    assert tool.invoke(invalid, approved(tool, invalid, context(tmp_path))).error.code == Code.INVALID_ARGUMENTS


def test_capacity_is_bounded_and_terminal_session_controls_survive_workdir_rename(tmp_path, tool):
    folder = tmp_path / 'project'
    folder.mkdir()
    args = launch_args(folder, 'import time;time.sleep(60)', 'cmd', yield_time_ms=0)
    sessions = [invoke(tool, tmp_path, args) for _ in range(4)]
    assert tool.invoke(args, approved(tool, args, context(tmp_path))).error.code == Code.INVALID_ARGUMENTS
    for session in sessions:
        assert invoke(tool, tmp_path, {'action': 'stop', 'session_id': session['session_id']})['owned_processes_released']
    folder.rename(tmp_path / 'renamed')
    assert invoke(tool, tmp_path, {'action': 'stop', 'session_id': sessions[0]['session_id']})['owned_processes_released']


def test_no_launch_without_approval_and_session_controls_cannot_select_other_runtime(tmp_path, tool):
    args = launch_args(tmp_path, 'import time;time.sleep(60)', yield_time_ms=0)
    assert tool.invoke(args, context(tmp_path)).error.code == Code.PERMISSION_DENIED
    ctx = approved(tool, args, context(tmp_path))
    assert tool.invoke(args | {'background': False}, ctx).error.code == Code.PERMISSION_DENIED
    assert tool.invoke(args | {'session_timeout_seconds': 10}, ctx).error.code == Code.PERMISSION_DENIED
    assert tool.sessions.list()['sessions'] == []
    session = invoke(tool, tmp_path, args)
    other = ShellRunCapability()
    try:
        query = {'action': 'status', 'session_id': session['session_id']}
        assert other.invoke(query, context(tmp_path)).error.code == Code.NOT_FOUND
        stop = {'action': 'stop', 'session_id': session['session_id']}
        assert tool.invoke(stop, approved(tool, query, context(tmp_path))).error.code == Code.PERMISSION_DENIED
        assert tool.sessions.get(session['session_id']).snapshot()['running']
    finally:
        other.shutdown()


def test_monitor_error_still_releases_owned_descendants(tmp_path, tool, monkeypatch):
    started = invoke(tool, tmp_path, launch_args(tmp_path, SERVER))
    info = server_info(tmp_path)
    owned = [psutil.Process(pid) for pid in info['pids']]
    session = tool.sessions.get(started['session_id'])
    poll = session._process.poll
    failed = False
    def fail_once():
        nonlocal failed
        if not failed:
            failed = True
            raise OSError('synthetic monitor error')
        return poll()
    monkeypatch.setattr(session._process, 'poll', fail_once)
    wait_for(lambda: session.finished)
    wait_for(lambda: all(not p.is_running() for p in owned))
    assert session.snapshot()['owned_processes_released'] and not session.snapshot()['running']


def test_owned_close_releases_job_even_when_exit_status_query_fails(tmp_path, monkeypatch):
    process = start_owned_process([sys.executable, '-c', 'import time;time.sleep(60)'], cwd=tmp_path, env=os.environ.copy())
    owned = psutil.Process(process.pid)
    def fail():
        raise OSError('synthetic poll error')
    monkeypatch.setattr(process, 'poll', fail)
    with pytest.raises(OSError, match='synthetic'):
        process.close()
    wait_for(lambda: not owned.is_running())
    assert not process._release.alive
    process.close()


@pytest.mark.parametrize('args', [
    {'background': True}, {'action': 'status'}, {'action': 'stop', 'session_id': '1234'},
    {'action': 'list', 'command': 'echo bad'}, {'action': 'list', 'session_id': 'shell-' + 'a'*32},
    {'action': 'stop', 'session_id': 'shell-' + 'a'*32, 'output_offset': 4},
    {'action': 'run', 'command': 'echo x', 'workdir': '.', 'session_timeout_seconds': 28801},
])
def test_session_argument_rejections_precede_execution(args):
    with pytest.raises(ValueError):
        ShellRunArguments.model_validate(args)
