from pathlib import Path

import pytest

from tools.verify_complaint_repair import allowed_shell, prompts


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
