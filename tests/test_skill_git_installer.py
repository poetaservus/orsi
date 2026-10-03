"""Real Git objects, untrusted repository fixtures and Windows ownership checks."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from threading import Thread
from time import monotonic, sleep

import pytest

from app.runtime.cancellation import CancellationSource
from app.runtime.skills import GitSkillInstaller, SkillInstaller, SkillRegistry, SkillInstallError
from app.runtime.skills.installer import SkillInstallErrorCode as Code
from app.runtime.skills import git_installer as module
from app.runtime.skills import _git_process as ownership
from app.runtime.skills.cli import main as cli


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows Git skill installer")
ROOT = Path(__file__).resolve().parents[1]
URL = "https://fixture.example/skills.git"
GIT = shutil.which("git")


def git(repo, *args, data=None):
    if GIT is None:
        pytest.skip("Git fixture executable is unavailable")
    env = module._environment()
    env.update(GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.test",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.test")
    result = subprocess.run([GIT, "-c", "core.autocrlf=false", "-c", "core.hooksPath=NUL", "-C", str(repo), *args],
                            input=data, capture_output=True, env=env, timeout=15)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def skill(name="frontend", body="PRIVATE-BODY"):
    return (f"---\nname: {json.dumps(name)}\ndescription: Fixture guidance.\n---\n{body}\n").encode()


def repository(tmp_path, files=None):
    path = tmp_path / "source"
    path.mkdir()
    git(path, "init", "--initial-branch=main")
    for name, data in (files if files is not None else {"skills/design/SKILL.md": skill()}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    git(path, "add", ".")
    git(path, "commit", "--allow-empty", "-m", "Fixture")
    return path


@pytest.fixture(autouse=True)
def contained_temp(tmp_path, monkeypatch):
    temporary = tmp_path / "downloads"
    temporary.mkdir()
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(temporary))
    yield
    # On every normal and rejected fixture, temporary objects/handles are gone.
    assert list(temporary.iterdir()) == []
    temporary.rename(tmp_path / "downloads-released")


def manager(tmp_path):
    return GitSkillInstaller(SkillInstaller(SkillRegistry(global_root=tmp_path / "storage")))


def local_transport(monkeypatch, repo):
    """Only the download seam is replaced. All production Git object inspection runs.

    The test-only file transport stays unavailable to production callers.
    """
    def clone(self, url, destination):
        assert url == URL
        self.run(["-c", "protocol.file.allow=always", "clone", "--bare", "--depth=1",
                  "--single-branch", "--no-tags", "--no-local", f"--template={self.empty}",
                  "--", repo.as_uri(), str(destination)], 0)
    monkeypatch.setattr(module._Git, "clone", clone)


def reject(code, call):
    with pytest.raises(SkillInstallError) as caught:
        call()
    assert caught.value.code == code
    assert "PRIVATE" not in str(caught.value)


def test_real_git_snapshot_preview_idempotence_and_remove(tmp_path, monkeypatch):
    exact = b'\xef\xbb\xbf---\r\nname: frontend\r\ndescription: Design\r\n---\r\n# Exact \xf0\x9f\x8e\xa8\r\n'
    repo = repository(tmp_path, {".github/skills/design/SKILL.md": exact,
                                 "skills/sql/SKILL.md": skill("sql-analysis")})
    revision = git(repo, "rev-parse", "HEAD").decode()
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    preview = []
    def inspect(skills):
        assert not installer.installer.storage_root.exists()
        assert not list((tmp_path / "downloads").iterdir())
        preview.extend(skills)
        skills[0].metadata["untrusted-change"] = True
    result = installer.install(URL, on_discovered=inspect)
    assert result.installed == ("frontend", "sql-analysis") and result.revision == revision
    installed = installer.installer.info("frontend")
    assert installed.source_path.read_bytes() == exact
    assert "untrusted-change" not in installed.metadata
    assert all(not item.source_path.exists() for item in preview)
    assert installer.install(URL).already_installed == result.installed
    installer.installer.remove("frontend")
    installer.installer.remove("sql-analysis")
    assert installer.installer.list() == ()


@pytest.mark.parametrize("files,code", [
    ({"README.md": b"Ordinary repository"}, Code.NO_SKILLS),
    ({}, Code.NO_SKILLS),
    ({"good/SKILL.md": skill(), "bad/SKILL.md": b"PRIVATE-BROKEN"}, Code.INVALID_PACKAGE),
    ({"a/SKILL.md": skill("same"), "b/SKILL.md": skill("same")}, Code.DUPLICATE_NAME),
])
def test_untrusted_fixtures_reject_before_storage_creation(tmp_path, monkeypatch, files, code):
    repo = repository(tmp_path, files)
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    reject(code, lambda: installer.install(URL))
    assert not installer.installer.storage_root.exists()


def test_scripts_attributes_hooks_and_inherited_config_never_execute(tmp_path, monkeypatch):
    sentinel = tmp_path / "executed.txt"
    script = f"from pathlib import Path; Path({str(sentinel)!r}).write_text('executed')".encode()
    repo = repository(tmp_path, {"SKILL.md": skill(), "setup.py": script, "install.sh": script,
        "scripts/postinstall.py": script, "package.json": b'{"scripts":{"postinstall":"exit 99"}}',
        ".gitmodules": b'[submodule "evil"]\npath = evil\nurl = ext::evil\n'})
    (repo / ".gitattributes").write_bytes(b"SKILL.md filter=evil diff=evil working-tree-encoding=UTF-16\n")
    git(repo, "add", ".gitattributes")
    # Git executable mode is permitted as inert content; only SKILL.md is copied.
    git(repo, "update-index", "--chmod=+x", "install.sh")
    git(repo, "commit", "-m", "Executable fixture")
    global_config = tmp_path / "evil.gitconfig"
    command = f'"{sys.executable}" -c "{script.decode()}"'
    global_config.write_text(f'[filter "evil"]\nsmudge = {command}\nrequired = true\n'
                             f'[core]\nhooksPath = {repo.as_posix()}/hooks\n'
                             f'[credential]\nhelper = !{command}\n')
    hooks = repo / "hooks"
    hooks.mkdir()
    (hooks / "post-checkout").write_bytes(script)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hooks))
    monkeypatch.setenv("GIT_SSH_COMMAND", command)
    monkeypatch.setenv("GIT_ASKPASS", command)
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    assert installer.install(URL).installed == ("frontend",)
    installed = installer.installer.info("frontend")
    assert installed.source_path.read_bytes() == skill()
    assert [path.name for path in installed.root_path.iterdir()] == ["SKILL.md"]
    assert not sentinel.exists()


@pytest.mark.parametrize("mode,name", [("120000", "SKILL.md"), ("120000", "resource-link"),
                                        ("160000", "module")])
def test_committed_symlinks_and_submodules_rejected_without_checkout(tmp_path, monkeypatch, mode, name):
    repo = repository(tmp_path)
    oid = git(repo, "rev-parse", "HEAD") if mode == "160000" else git(repo, "hash-object", "-w", "--stdin", data=b"../outside")
    git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid.decode()},{name}")
    git(repo, "commit", "-m", "Unsafe fixture")
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    reject(Code.UNSAFE_REPOSITORY, lambda: installer.install(URL))
    assert not installer.installer.storage_root.exists()


@pytest.mark.parametrize("limit", ["blob", "skill", "entries", "bytes", "tree"])
def test_repository_limits_reject_before_copy(tmp_path, monkeypatch, limit):
    repo = repository(tmp_path, {"SKILL.md": skill(), "huge.bin": b"x" * 4096})
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    code = Code.DOWNLOAD_LIMIT
    if limit == "blob":
        monkeypatch.setattr(module, "MAX_REPOSITORY_BLOB_BYTES", 1024)
    elif limit == "skill":
        installer.installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "storage", max_bytes=32))
        code = Code.LIMIT_EXCEEDED
    elif limit == "entries":
        monkeypatch.setattr(module, "MAX_TREE_ENTRIES", 1)
    elif limit == "bytes":
        monkeypatch.setattr(module, "MAX_DOWNLOAD_BYTES", 256)
    else:
        monkeypatch.setattr(module, "MAX_TREE_BYTES", 16)
    reject(code, lambda: installer.install(URL))
    assert not installer.installer.storage_root.exists()


@pytest.mark.parametrize("url", [None, "", "http://fixture.example/repo", "git://fixture.example/repo",
    "ssh://fixture.example/repo", "file:///repo", "git@fixture.example:repo", "ext::evil",
    "https://user@fixture.example/repo", "https://user:PRIVATE@fixture.example/repo",
    "https://fixture.example/repo?ref=main", "https://fixture.example/repo#branch",
    "https://fixture.example/repo?", "https://fixture.example/repo#", "https://fixture.example/",
    "https://fixture.example:0/repo", "https://fixture.example:65536/repo",
    "https://fixture.example/repo\nPRIVATE", "https://fixture.example/repo path",
    "https://fixture.example\\repo", "https://fixture.example/%0aPRIVATE", "https://%66ixture.example/repo",
    "https://-invalid.example/repo", "https://fixture.example/" + "x" * 2048])
def test_invalid_urls_never_launch_or_create_storage(tmp_path, monkeypatch, url):
    monkeypatch.setattr(module.shutil, "which", lambda _: pytest.fail("URL must be validated first"))
    installer = manager(tmp_path)
    reject(Code.INVALID_REMOTE, lambda: installer.install(url))
    assert not installer.installer.storage_root.exists()


def test_missing_git_does_not_create_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    reject(Code.GIT_UNAVAILABLE, lambda: manager(tmp_path).install(URL))
    assert not (tmp_path / "storage").exists()


def test_clone_flags_and_environment_are_isolated(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "url.ext::PRIVATE.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://")
    monkeypatch.setenv("GIT_EXEC_PATH", "PRIVATE")
    monkeypatch.setenv("SSH_ASKPASS", "PRIVATE")
    def run(self, args, limit):
        calls.append((self.prefix + args, self.env, limit))
        raise SkillInstallError(Code.DOWNLOAD_FAILED, "Fixture download failure.")
    monkeypatch.setattr(module._Git, "run", run)
    reject(Code.DOWNLOAD_FAILED, lambda: manager(tmp_path).install(URL))
    args, env, limit = calls[0]
    assert "--bare" in args and "--no-local" in args and "--depth=1" in args
    assert args[-2] == URL and args[-3] == "--" and limit == 0
    assert "protocol.allow=never" in args and "protocol.https.allow=always" in args
    assert "http.followRedirects=false" in args and "credential.helper=" in args
    assert not any(key in env for key in ("GIT_CONFIG_COUNT", "GIT_EXEC_PATH", "SSH_ASKPASS"))
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == os.devnull


def test_cancelled_download_and_preview_do_not_publish(tmp_path, monkeypatch):
    source = CancellationSource()
    source.cancel("PRIVATE reason")
    reject(Code.CANCELLED, lambda: manager(tmp_path).install(URL, cancellation=source.token))
    repo = repository(tmp_path)
    local_transport(monkeypatch, repo)
    source = CancellationSource()
    reject(Code.CANCELLED, lambda: manager(tmp_path).install(URL, cancellation=source.token,
                                     on_discovered=lambda _: source.cancel("PRIVATE")))
    assert not (tmp_path / "storage").exists()


@pytest.mark.parametrize("stop", ["timeout", "cancel", "output", "failure"])
def test_owned_git_command_stops_descendants_on_all_exit_paths(tmp_path, monkeypatch, stop):
    report = tmp_path / "child-pid"
    source = CancellationSource()
    child = "import time; time.sleep(60)"
    code = ("import subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}],creationflags=0x08000000); "
            f"open({str(report)!r},'w').write(str(p.pid)); " +
            ("print('PRIVATE',flush=True); time.sleep(60)" if stop == "output" else
             "raise SystemExit(9)" if stop == "failure" else "time.sleep(60)"))
    real_start = ownership.start_owned_process
    spawned = []
    def start(_command, **kwargs):
        process = real_start([sys.executable, "-c", code], **kwargs)
        spawned.append(process)
        return process
    monkeypatch.setattr(ownership, "start_owned_process", start)
    def cancel_after_started():
        deadline = monotonic() + 5
        while not report.exists() and monotonic() < deadline:
            sleep(0.01)
        if stop == "cancel":
            source.cancel("PRIVATE")
    thread = Thread(target=cancel_after_started)
    thread.start()
    try:
        with module._workspace() as workspace:
            empty = workspace / "empty"
            empty.mkdir()
            runner = module._Git(GIT, workspace, empty, source.token,
                                 monotonic() + (1.0 if stop == "timeout" else 10))
            expected = {"timeout": Code.TIMED_OUT, "cancel": Code.CANCELLED,
                        "output": Code.DOWNLOAD_LIMIT, "failure": Code.DOWNLOAD_FAILED}[stop]
            reject(expected, lambda: runner.run(["unused"], 0))
            assert spawned[0].poll() is not None
            assert not list(workspace.glob("output-*"))
        assert report.exists()
        api = ownership._api()
        api.OpenProcess.argtypes, api.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        handle = api.OpenProcess(0x100000, False, int(report.read_text()))
        if handle:
            try:
                assert api.WaitForSingleObject(handle, 5000) == 0
            finally:
                api.CloseHandle(handle)
    finally:
        thread.join(5)
        for process in spawned:
            process.close()


def test_job_ownership_failure_prevents_child_creation(tmp_path, monkeypatch):
    real = ownership._api()
    class FailedJob:
        def __getattr__(self, name):
            return getattr(real, name)
        def UpdateProcThreadAttribute(self, *args):
            return False
        def CreateProcessW(self, *args):
            pytest.fail("Never start a Git child without ownership")
    monkeypatch.setattr(ownership, "_api", lambda: FailedJob())
    reject(Code.DOWNLOAD_FAILED, lambda: manager(tmp_path).install(URL))


def test_cleanup_readonly_and_handle_release(tmp_path):
    with module._workspace() as workspace:
        nested = workspace / "nested"
        nested.mkdir()
        file = nested / "pack.bin"
        file.write_bytes(b"owned")
        file.chmod(stat.S_IREAD)
    assert not workspace.exists()


def test_cleanup_failure_prevents_publication(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    local_transport(monkeypatch, repo)
    real_delete = module._delete_file
    monkeypatch.setattr(module, "_delete_file", lambda _: (_ for _ in ()).throw(OSError("PRIVATE")))
    try:
        reject(Code.CLEANUP_FAILED, lambda: manager(tmp_path).install(URL))
        assert not (tmp_path / "storage").exists()
        leftovers = list((tmp_path / "downloads").iterdir())
        assert len(leftovers) == 1
    finally:
        monkeypatch.setattr(module, "_delete_file", real_delete)
        for folder in (tmp_path / "downloads").iterdir():
            module._clean_contents(folder)
            folder.rmdir()


def test_cli_remote_preview_revision_and_metadata_only(tmp_path, monkeypatch, capsys):
    repo = repository(tmp_path)
    local_transport(monkeypatch, repo)
    assert cli(["--storage", str(tmp_path / "storage"), "install", URL]) == 0
    output = capsys.readouterr()
    assert output.out.index("Validated Git skills") < output.out.index("Installed")
    assert git(repo, "rev-parse", "HEAD").decode() in output.out
    assert "PRIVATE" not in output.out + output.err
    assert cli(["--storage", str(tmp_path / "storage"), "install", "ssh://PRIVATE/repo"]) == 1
    assert "PRIVATE" not in capsys.readouterr().err


def test_remote_cli_has_no_inference_ui_imports(tmp_path):
    repo = repository(tmp_path)
    storage = tmp_path / "storage"
    code = '''
import sys
from pathlib import Path
class BlockRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('app.inference', 'app.ui', 'app.startup', 'PySide6')):
            raise AssertionError('Skill management must not start UI or inference')
sys.meta_path.insert(0, BlockRuntime())
from app.runtime.skills.git_installer import _Git
fixture = Path(sys.argv[2])
def clone(self, url, destination):
    self.run(['-c','protocol.file.allow=always','clone','--bare','--depth=1','--no-local',
              '--template='+str(self.empty),'--',fixture.as_uri(),str(destination)],0)
_Git.clone = clone
from app.main import main
sys.argv = ['orsi','skill','--storage',sys.argv[1],'install','https://fixture.example/repo']
raise SystemExit(main())
'''
    # A separate interpreter exercises the production command entry point with
    # real Git object reads and the same test-only transport substitution.
    result = subprocess.run([sys.executable, "-B", "-c", code, str(storage), str(repo)],
                            cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert SkillRegistry(global_root=storage).discover().skills[0].name == "frontend"


@pytest.mark.parametrize("kind", ["count", "total"])
def test_multi_skill_limits_are_atomic(tmp_path, monkeypatch, kind):
    repo = repository(tmp_path, {"a/SKILL.md": skill("one"), "b/SKILL.md": skill("two")})
    local_transport(monkeypatch, repo)
    monkeypatch.setattr(module, "MAX_INSTALL_SKILLS" if kind == "count" else "MAX_INSTALL_BYTES",
                        1 if kind == "count" else len(skill("one")) + 1)
    reject(Code.LIMIT_EXCEEDED, lambda: manager(tmp_path).install(URL))
    assert not (tmp_path / "storage").exists()


@pytest.mark.parametrize("record", [b"invalid\0", b"100644 blob invalid 1\tSKILL.md\0",
    b"100644 blob " + b"a" * 40 + b" -1\tSKILL.md\0",
    b"100644 blob " + b"a" * 40 + b" 1\t\0",
    b"100644 blob " + b"a" * 40 + b" 1\tSKILL.md"])
def test_invalid_tree_records_reject(record):
    reject(Code.UNSAFE_REPOSITORY, lambda: module._skill_blobs(record, 1024))


def test_untrusted_git_path_never_becomes_a_local_path():
    oid = b"a" * 40
    record = b"100644 blob " + oid + b" 64\t../../CON:evil/SKILL.md\0"
    assert module._skill_blobs(record, 1024) == ((oid.decode(), 64),)


def test_preview_failure_does_not_create_storage(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    local_transport(monkeypatch, repo)
    def fail(_):
        raise RuntimeError("Caller preview failure")
    with pytest.raises(RuntimeError, match="Caller preview"):
        manager(tmp_path).install(URL, on_discovered=fail)
    assert not (tmp_path / "storage").exists()


def test_actual_temporary_junction_never_follows_external_files(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "PRIVATE-preserved.txt"
    sentinel.write_text("preserved")
    root = None
    try:
        with pytest.raises(SkillInstallError) as error:
            with module._workspace() as root:
                link = root / "redirect"
                command = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                         capture_output=True, text=True, timeout=5)
                assert command.returncode == 0, command.stderr
                reject(Code.UNSAFE_REPOSITORY, lambda: module._check_download(root))
        assert error.value.code == Code.CLEANUP_FAILED
        assert sentinel.read_text() == "preserved"
    finally:
        if root is not None and root.exists():
            (root / "redirect").rmdir()  # Remove only the junction, never its target.
            root.rmdir()
