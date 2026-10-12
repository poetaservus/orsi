from pathlib import Path

import pytest

from tools.verify_complaint_repair import allowed_shell, prompts, remaining_owned_processes
from tools.scroll_acceptance import preview_reference_allowed


def test_original_replay_prompts_are_unchanged_except_the_fixture_path():
    assert prompts(Path('fixture')) == [
        'can inspect and summarize this project please fixture',
        'can you start the npm server in the anim folder?',
        'great. currently the first section animation is disabled, can you re-enable it?\\']


@pytest.mark.parametrize('command,allowed', [
    ('npm.cmd run dev -- --host 127.0.0.1',True),('npm run build',True),
    ('npm.cmd run dev -- --host 127.0.0.1 --port 12345',True),
    ('npm run build; Remove-Item C:/private',False),('npm run dev -- --host 0.0.0.0',False),
    ('npm run build && echo secret',False),('powershell.exe -Command anything',False)])
def test_live_harness_approves_only_reviewed_project_commands(tmp_path, command, allowed):
    assert allowed_shell(dict(action='run',workdir=str(tmp_path),command=command),tmp_path) is allowed
    assert not allowed_shell(dict(action='run',workdir=str(tmp_path.parent),command=command),tmp_path)


@pytest.mark.parametrize('reference,allowed', [
    ('http://127.0.0.1:1234/assets/logo.png',True),('ws://127.0.0.1:1234/',True),
    ('https://api.openai.com/v1/responses',False),('http://127.0.0.1:2345/',False),
    ('http://user:pass@127.0.0.1:1234/',False),('file:///C:/private.txt',False)])
def test_independent_oracle_only_requests_its_local_origin(reference, allowed):
    assert preview_reference_allowed(reference,'http://127.0.0.1:1234/') is allowed


def test_live_cleanup_distinguishes_owned_process_from_pid_reuse():
    from types import SimpleNamespace
    def lookup(pid):
        if pid == 3:
            raise OSError('already exited')
        return SimpleNamespace(create_time=lambda: {1:10,2:99}[pid])
    assert remaining_owned_processes({(1,10),(2,20),(3,30)},lookup) == [1]
