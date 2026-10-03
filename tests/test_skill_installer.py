"""Real local transactions, unsupported-resource isolation and command entry points."""
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread

import pytest

from app.runtime.skills import SkillInstaller, SkillInstallError, SkillInstallErrorCode, SkillRegistry
from app.runtime.skills import installer as module
from app.runtime.skills.cli import main as cli


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows local skill installer")
REPO = Path(__file__).resolve().parents[1]


def write_skill(folder, name="frontend", body="PRIVATE-INSTRUCTIONS", data=None):
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "SKILL.md"
    source.write_bytes(data if data is not None else
        ("---\nname: " + json.dumps(name, ensure_ascii=False) + "\ndescription: Local design guidance.\n"
         "metadata: {shell_enabled: true}\n---\n" + body).encode("utf-8"))
    return source


def manager(tmp_path, **kwargs):
    return SkillInstaller(SkillRegistry(global_root=tmp_path / "storage", **kwargs))


def reject(code, call):
    with pytest.raises(SkillInstallError) as caught:
        call()
    assert caught.value.code == code
    assert "PRIVATE" not in str(caught.value)
    return caught.value


def assert_clean(tmp_path, installer, names=()):
    assert tuple(s.name for s in installer.registry.list()) == names
    assert not list(tmp_path.glob(".orsi-skill-*"))
    assert not module._lock_path(installer.storage_root).exists()


def test_single_skill_preview_precedes_copy_and_preserves_exact_bytes(tmp_path):
    source = write_skill(tmp_path / "source", data=
        b'\xef\xbb\xbf---\r\nname: frontend\r\ndescription: Design\r\n---\r\n# Exact \xf0\x9f\x8e\xa8\r\n')
    installer = manager(tmp_path)
    preview = []
    def inspect(skills):
        assert not installer.storage_root.exists()
        preview.extend(skills)
    result = installer.install(source.parent, on_discovered=inspect)
    assert result.installed == ("frontend",) and not result.already_installed
    skill = installer.registry.get("frontend")
    assert preview[0].root_path == source.parent and skill.root_path.parent == installer.storage_root
    assert skill.source_path.read_bytes() == source.read_bytes()
    assert skill.instructions == "# Exact 🎨\r\n"
    assert [p.name for p in skill.root_path.iterdir()] == ["SKILL.md"]
    assert_clean(tmp_path, installer, ("frontend",))
    source.parent.rename(tmp_path / "source-handles-released")
    installer.storage_root.rename(tmp_path / "storage-handles-released")


def test_nested_repository_installs_multiple_skills_without_resources_or_execution(tmp_path):
    repo = tmp_path / "repo"
    first = write_skill(repo / ".github" / "skills" / "design", "frontend")
    write_skill(repo / "skills" / "sql", "sql-analysis")
    sentinel = tmp_path / "executed.txt"
    (repo / "setup.py").write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')")
    (first.parent / "install.py").write_text("raise RuntimeError('Never execute')")
    (first.parent / "references").mkdir()
    (first.parent / "references" / "large.bin").write_bytes(b"ignored")
    (first.parent / "package.json").write_text('{"scripts":{"postinstall":"exit 1"}}')
    installer = manager(tmp_path)
    result = installer.install(repo)
    assert result.installed == ("frontend", "sql-analysis")
    assert not sentinel.exists()
    assert all([p.name for p in s.root_path.iterdir()] == ["SKILL.md"] for s in installer.list())
    assert_clean(tmp_path, installer, ("frontend", "sql-analysis"))


def test_duplicate_names_reject_entire_batch_before_writing(tmp_path):
    repo = tmp_path / "repo"
    write_skill(repo / "first", "same")
    write_skill(repo / "second", "same")
    installer = manager(tmp_path)
    reject(SkillInstallErrorCode.DUPLICATE_NAME, lambda: installer.install(repo))
    assert not installer.storage_root.exists()


@pytest.mark.parametrize("data", [b"PRIVATE-BROKEN", b"\xffPRIVATE-BROKEN",
    b"---\nname: x\n---\nPRIVATE-BROKEN", b"---\nname: [x]\ndescription: ok\n---\nPRIVATE-BROKEN"])
def test_malformed_skill_prevents_partial_installation(tmp_path, data):
    write_skill(tmp_path / "repo" / "a-valid", "valid")
    write_skill(tmp_path / "repo" / "z-invalid", data=data)
    installer = manager(tmp_path)
    reject(SkillInstallErrorCode.INVALID_PACKAGE, lambda: installer.install(tmp_path / "repo"))
    assert not installer.storage_root.exists()


def test_no_skills_does_not_create_storage(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("ordinary repository")
    installer = manager(tmp_path)
    reject(SkillInstallErrorCode.NO_SKILLS, lambda: installer.install(repo))
    assert not installer.storage_root.exists()


def test_reinstall_is_idempotent_changed_content_requires_removal(tmp_path):
    source = write_skill(tmp_path / "source")
    installer = manager(tmp_path)
    installer.install(source.parent)
    original = installer.info("frontend").source_path.read_bytes()
    result = installer.install(source.parent)
    assert not result.installed and result.already_installed == ("frontend",)
    source.write_bytes(source.read_bytes() + b"\nnew body")
    reject(SkillInstallErrorCode.CONFLICT, lambda: installer.install(source.parent))
    assert installer.info("frontend").source_path.read_bytes() == original
    installer.remove("frontend")
    assert installer.registry.get("frontend") is None
    installer.install(source.parent)
    assert installer.info("frontend").source_path.read_bytes() == source.read_bytes()
    assert_clean(tmp_path, installer, ("frontend",))


def test_conflict_in_batch_does_not_install_other_skills(tmp_path):
    write_skill(tmp_path / "original", "same", "original")
    installer = manager(tmp_path)
    installer.install(tmp_path / "original")
    write_skill(tmp_path / "repo" / "a-new", "new")
    write_skill(tmp_path / "repo" / "z-conflict", "same", "replacement")
    reject(SkillInstallErrorCode.CONFLICT, lambda: installer.install(tmp_path / "repo"))
    assert_clean(tmp_path, installer, ("same",))
    assert installer.info("same").instructions == "original"


def test_preview_is_detached_and_install_uses_validated_snapshot(tmp_path):
    source = write_skill(tmp_path / "source")
    original = source.read_bytes()
    installer = manager(tmp_path)
    def preview(skills):
        skills[0].metadata.clear()
        source.write_bytes(b"Changed after preview")
    installer.install(source.parent, on_discovered=preview)
    assert installer.info("frontend").source_path.read_bytes() == original
    assert installer.info("frontend").metadata == {"metadata": {"shell_enabled": True}}


def test_preview_failure_makes_no_storage_changes(tmp_path):
    source = write_skill(tmp_path / "source")
    installer = manager(tmp_path)
    def fail(_skills):
        raise RuntimeError("preview stopped")
    with pytest.raises(RuntimeError, match="preview stopped"):
        installer.install(source.parent, on_discovered=fail)
    assert not installer.storage_root.exists()


@pytest.mark.parametrize("operation", ["write", "publish"])
def test_partial_failure_rolls_back_batch_and_refreshes_existing_catalog(tmp_path, monkeypatch, operation):
    installer = manager(tmp_path)
    write_skill(tmp_path / "original", "original")
    installer.install(tmp_path / "original")
    write_skill(tmp_path / "repo" / "first", "first")
    write_skill(tmp_path / "repo" / "second", "second")
    function_name = "_write_package" if operation == "write" else "_publish"
    real = getattr(module, function_name)
    count = 0
    def fail_second(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("PRIVATE failure details")
        return real(*args)
    monkeypatch.setattr(module, function_name, fail_second)
    reject(SkillInstallErrorCode.IO_ERROR, lambda: installer.install(tmp_path / "repo"))
    assert_clean(tmp_path, installer, ("original",))
    assert len(tuple(installer.storage_root.iterdir())) == 1
    installer.storage_root.rename(tmp_path / "released-storage")


def test_registry_refresh_failure_rolls_back_installed_content(tmp_path, monkeypatch):
    write_skill(tmp_path / "source")
    installer = manager(tmp_path)
    real, count = installer.registry.reload, 0
    def fail_once():
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("PRIVATE refresh details")
        return real()
    monkeypatch.setattr(installer.registry, "reload", fail_once)
    reject(SkillInstallErrorCode.REFRESH_FAILED, lambda: installer.install(tmp_path / "source"))
    assert_clean(tmp_path, installer)
    assert not tuple(installer.storage_root.iterdir())


def test_changed_staged_bytes_are_rejected_after_placement(tmp_path, monkeypatch):
    write_skill(tmp_path / "source")
    installer = manager(tmp_path)
    real = module._publish
    def change_before_publish(source, destination, identity):
        (source / "SKILL.md").write_bytes(b"unexpected change")
        real(source, destination, identity)
    monkeypatch.setattr(module, "_publish", change_before_publish)
    reject(SkillInstallErrorCode.IO_ERROR, lambda: installer.install(tmp_path / "source"))
    assert_clean(tmp_path, installer)
    assert not tuple(installer.storage_root.iterdir())


def test_removal_refresh_failure_restores_original_skill(tmp_path, monkeypatch):
    write_skill(tmp_path / "source")
    installer = manager(tmp_path)
    installer.install(tmp_path / "source")
    real, count = installer.registry.reload, 0
    def fail_once():
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("PRIVATE refresh details")
        return real()
    monkeypatch.setattr(installer.registry, "reload", fail_once)
    reject(SkillInstallErrorCode.REFRESH_FAILED, lambda: installer.remove("frontend"))
    assert_clean(tmp_path, installer, ("frontend",))


def test_rollback_failure_is_reported_and_does_not_delete_unknown_resources(tmp_path, monkeypatch):
    write_skill(tmp_path / "source")
    installer = manager(tmp_path)
    real = module._write_package
    def fail_with_extra(folder, identity, data):
        real(folder, identity, data)
        (folder / "unexpected.txt").write_text("preserve")
        raise OSError("PRIVATE failure")
    monkeypatch.setattr(module, "_write_package", fail_with_extra)
    reject(SkillInstallErrorCode.ROLLBACK_FAILED, lambda: installer.install(tmp_path / "source"))
    stages = tuple(tmp_path.glob(".orsi-skill-stage-*"))
    assert len(stages) == 1 and (stages[0] / "unexpected.txt").read_text() == "preserve"
    assert installer.registry.list() == ()
    assert not module._lock_path(installer.storage_root).exists()


def test_removal_refuses_extra_resources_and_project_only_skill(tmp_path):
    installer = manager(tmp_path, project_root=tmp_path / "project")
    write_skill(installer.storage_root / "manual", "manual")
    (installer.storage_root / "manual" / "keep.txt").write_text("keep")
    write_skill(tmp_path / "project" / ".orsi" / "skills" / "project", "project-only")
    reject(SkillInstallErrorCode.UNSUPPORTED_RESOURCES, lambda: installer.remove("manual"))
    reject(SkillInstallErrorCode.NOT_FOUND, lambda: installer.remove("project-only"))
    assert (installer.storage_root / "manual" / "keep.txt").read_text() == "keep"
    assert installer.info("project-only").root_path.is_relative_to(tmp_path / "project")


def test_removal_reveals_project_override_without_deleting_it(tmp_path):
    installer = manager(tmp_path, project_root=tmp_path / "project")
    write_skill(tmp_path / "source", "shared", "global")
    project_source = write_skill(tmp_path / "project" / ".orsi" / "skills" / "shared", "shared", "project")
    installer.install(tmp_path / "source")
    assert installer.registry.get("shared").instructions == "project"
    installer.remove("shared")
    assert installer.registry.get("shared").source_path == project_source
    assert not tuple(installer.storage_root.iterdir())


def test_global_storage_rejections_block_mutations(tmp_path):
    installer = manager(tmp_path)
    write_skill(tmp_path / "source")
    write_skill(installer.storage_root / "broken", data=b"PRIVATE malformed")
    reject(SkillInstallErrorCode.STORAGE_REJECTED, lambda: installer.install(tmp_path / "source"))
    assert len(tuple(installer.storage_root.iterdir())) == 1


def test_existing_destination_is_never_overwritten(tmp_path):
    installer = manager(tmp_path)
    write_skill(tmp_path / "source")
    destination = installer.storage_root / module._folder_name("frontend")
    destination.mkdir(parents=True)
    (destination / "keep.txt").write_text("preserve")
    reject(SkillInstallErrorCode.CONFLICT, lambda: installer.install(tmp_path / "source"))
    assert (destination / "keep.txt").read_text() == "preserve"


def test_busy_lock_is_preserved_and_no_package_is_written(tmp_path):
    installer = manager(tmp_path)
    installer.storage_root.mkdir()
    lock = module._lock_path(installer.storage_root)
    lock.write_text("other operation")
    write_skill(tmp_path / "source")
    reject(SkillInstallErrorCode.BUSY, lambda: installer.install(tmp_path / "source"))
    assert lock.read_text() == "other operation"
    assert not list(installer.storage_root.iterdir())


def test_two_installer_instances_do_not_interleave_transactions(tmp_path, monkeypatch):
    first, second = manager(tmp_path), manager(tmp_path)
    write_skill(tmp_path / "source1", "first")
    write_skill(tmp_path / "source2", "second")
    entered, release = Event(), Event()
    real = module._write_package
    failures = []
    def paused(*args):
        entered.set()
        assert release.wait(5)
        return real(*args)
    monkeypatch.setattr(module, "_write_package", paused)
    def install_first():
        try:
            first.install(tmp_path / "source1")
        except BaseException as error:
            failures.append(error)
    worker = Thread(target=install_first)
    worker.start()
    try:
        assert entered.wait(5)
        reject(SkillInstallErrorCode.BUSY, lambda: second.install(tmp_path / "source2"))
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and not failures
    assert_clean(tmp_path, first, ("first",))


@pytest.mark.parametrize("limit", ["skills", "bytes", "entries", "depth", "file", "capacity"])
def test_installation_limits_reject_before_any_package_is_committed(tmp_path, monkeypatch, limit):
    repo = tmp_path / "repo"
    write_skill(repo / "first", "first")
    write_skill(repo / "second", "second")
    kwargs = {}
    expected = SkillInstallErrorCode.LIMIT_EXCEEDED
    if limit == "skills":
        monkeypatch.setattr(module, "MAX_INSTALL_SKILLS", 1)
    elif limit == "bytes":
        monkeypatch.setattr(module, "MAX_INSTALL_BYTES", 1)
    elif limit == "entries":
        monkeypatch.setattr(module, "MAX_INSTALL_ENTRIES", 1)
    elif limit == "depth":
        monkeypatch.setattr(module, "MAX_INSTALL_DEPTH", 0)
    elif limit == "file":
        kwargs["max_bytes"] = 1
        expected = SkillInstallErrorCode.INVALID_PACKAGE
    else:
        kwargs["max_entries"] = 1
    installer = manager(tmp_path, **kwargs)
    reject(expected, lambda: installer.install(repo))
    assert installer.registry.list() == ()
    assert not installer.storage_root.exists() or not tuple(installer.storage_root.iterdir())


@pytest.mark.parametrize("name", ["../escape", "CON", "x:y", "Name\nwith controls", "Case", "case", "🎨 design"])
def test_metadata_names_are_never_filesystem_components(tmp_path, name):
    installer = manager(tmp_path)
    write_skill(tmp_path / "source", name)
    installer.install(tmp_path / "source")
    skill = installer.info(name)
    assert skill.root_path.parent == installer.storage_root
    assert skill.root_path.name.startswith("skill-") and len(skill.root_path.name) == 70
    installer.remove(name)
    assert_clean(tmp_path, installer)


@pytest.mark.parametrize("location", ["source", "ancestor", "repository_child", "storage"])
def test_junctions_cannot_redirect_source_or_storage(tmp_path, location):
    import _winapi
    installer = manager(tmp_path)
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    write_skill(outside)
    if location == "source":
        _winapi.CreateJunction(str(outside), str(source))
    elif location == "ancestor":
        _winapi.CreateJunction(str(tmp_path), str(tmp_path / "alias"))
        source = tmp_path / "alias" / "outside"
    elif location == "repository_child":
        source.mkdir()
        _winapi.CreateJunction(str(outside), str(source / "link"))
    else:
        write_skill(source)
        _winapi.CreateJunction(str(outside), str(installer.storage_root))
    reject(SkillInstallErrorCode.UNSAFE_PATH if location != "storage" else SkillInstallErrorCode.STORAGE_REJECTED,
           lambda: installer.install(source))
    assert [p.name for p in outside.iterdir()] == ["SKILL.md"]


def test_unsupported_resources_inside_a_skill_are_not_traversed(tmp_path):
    import _winapi
    source = write_skill(tmp_path / "source")
    outside = tmp_path / "outside"
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(source.parent / "references"))
    installer = manager(tmp_path)
    installer.install(source.parent)
    assert [p.name for p in installer.info("frontend").root_path.iterdir()] == ["SKILL.md"]
    assert not tuple(outside.iterdir())


@pytest.mark.parametrize("source", [None, "local-directory", Path("../escape"), Path("https://example.test/repo"),
                                    Path(r"C:\source\SKILL.md:stream"), Path(r"\\host\share\repo")])
def test_invalid_or_remote_paths_are_rejected(tmp_path, source):
    installer = manager(tmp_path)
    with pytest.raises(SkillInstallError):
        installer.install(source)
    assert not installer.storage_root.exists()


def test_read_only_registry_configuration_and_invalid_inputs(tmp_path):
    installer = manager(tmp_path)
    assert installer.registry.global_root == tmp_path / "storage"
    for field in ("global_root", "max_bytes", "max_entries"):
        with pytest.raises(AttributeError):
            setattr(installer.registry, field, None)
    with pytest.raises(TypeError):
        SkillInstaller(object())
    for value in (None, "", " "):
        reject(SkillInstallErrorCode.INVALID_INPUT, lambda: installer.remove(value))
        reject(SkillInstallErrorCode.INVALID_INPUT, lambda: installer.info(value))
    write_skill(tmp_path / "source")
    with pytest.raises(TypeError):
        installer.install(tmp_path / "source", on_discovered=True)


def test_missing_removal_does_not_create_storage(tmp_path):
    installer = manager(tmp_path)
    reject(SkillInstallErrorCode.NOT_FOUND, lambda: installer.remove("missing"))
    assert not installer.storage_root.exists()


def test_install_refresh_reaches_existing_conversation_and_remove_invalidates_explicit_selection(tmp_path):
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.engine import InferenceEngine
    from app.runtime.skills import SkillActivationError
    from app.runtime.skills.selection import SELECTOR_SYSTEM_PROMPT
    class Model(InferenceEngine):
        context_length = 16384
        max_response_tokens = 128
        def __init__(self):
            self.answers = []
        def respond(self, messages):
            if messages[0]["content"] == SELECTOR_SYSTEM_PROMPT:
                assert "PRIVATE-INSTRUCTIONS" not in json.dumps(messages)
                return '{"skill": "frontend"}'
            self.answers.append(messages)
            return "reply"
    model, installer = Model(), manager(tmp_path)
    service = ConversationService(model, ConversationStore(tmp_path / "chat.json"), skill_registry=installer.registry)
    try:
        service.run("Design a frontend interface.")
        assert service.active_skill is None
        write_skill(tmp_path / "source")
        installer.install(tmp_path / "source")
        service.run("Design a frontend interface.")
        assert service.active_skill.name == "frontend"
        assert model.answers[-1][0]["content"].count("\nACTIVE SKILL\n") == 1
        assert "PRIVATE-INSTRUCTIONS" in model.answers[-1][0]["content"]
        service.activate_skill("frontend")
        installer.remove("frontend")
        count = len(model.answers)
        with pytest.raises(SkillActivationError):
            service.run("Design a frontend interface.")
        assert len(model.answers) == count
        service.new_session()
        service.run("Hello")
        assert service.active_skill is None and service.skill_selection.reason == "empty_catalog"
    finally:
        service.shutdown()


def test_case_distinct_names_do_not_collide_on_windows(tmp_path):
    installer = manager(tmp_path)
    write_skill(tmp_path / "repo" / "first", "Case")
    write_skill(tmp_path / "repo" / "second", "case")
    assert installer.install(tmp_path / "repo").installed == ("Case", "case")
    assert installer.info("Case").root_path != installer.info("case").root_path
    installer.remove("Case")
    assert installer.info("case").name == "case"


def test_exact_catalog_capacity_allows_install_and_removal(tmp_path):
    installer = manager(tmp_path, max_entries=2)
    write_skill(tmp_path / "repo" / "first", "first")
    write_skill(tmp_path / "repo" / "second", "second")
    installer.install(tmp_path / "repo")
    assert len(tuple(installer.storage_root.iterdir())) == 2
    assert tuple(s.name for s in installer.list()) == ("first", "second")
    installer.remove("first")
    assert_clean(tmp_path, installer, ("second",))


def test_file_growth_during_snapshot_is_bounded_and_has_structured_failure(tmp_path, monkeypatch):
    source = write_skill(tmp_path / "source")
    limit = len(source.read_bytes())
    installer = manager(tmp_path, max_bytes=limit)
    real = module._read_snapshot
    def grow(path, max_bytes):
        path.write_bytes(path.read_bytes() + b"growing")
        return real(path, max_bytes)
    monkeypatch.setattr(module, "_read_snapshot", grow)
    reject(SkillInstallErrorCode.INVALID_PACKAGE, lambda: installer.install(source.parent))
    assert not installer.storage_root.exists()


@pytest.mark.parametrize("kind", ["file", "missing"])
def test_install_requires_existing_directory(tmp_path, kind):
    installer = manager(tmp_path)
    source = tmp_path / "source"
    if kind == "file":
        source.write_text("PRIVATE file")
    reject(SkillInstallErrorCode.INVALID_INPUT if kind == "file" else SkillInstallErrorCode.IO_ERROR,
           lambda: installer.install(source))
    assert not installer.storage_root.exists()


def test_cli_all_four_commands_and_failure_exit_codes(tmp_path, capsys):
    installer = manager(tmp_path)
    source = write_skill(tmp_path / "source")
    args = ["--storage", str(installer.storage_root)]
    assert cli(args + ["list"]) == 0
    assert not installer.storage_root.exists()
    assert cli(args + ["install", str(source.parent)]) == 0
    output = capsys.readouterr().out
    assert output.index("Validated local skills") < output.index("Installed")
    assert "PRIVATE-INSTRUCTIONS" not in output
    assert cli(args + ["info", "frontend"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["supported_files"] == ["SKILL.md"] and "instructions" not in info
    assert cli(args + ["list"]) == 0 and "frontend" in capsys.readouterr().out
    assert cli(args + ["remove", "frontend"]) == 0
    assert cli(args + ["info", "frontend"]) == 1
    assert "not_found" in capsys.readouterr().err
    assert cli(args + ["install", "http://example.test/repo"]) == 1


def test_cli_list_reports_rejected_entries_separately(tmp_path, capsys):
    installer = manager(tmp_path)
    write_skill(installer.storage_root / "valid", "valid")
    write_skill(installer.storage_root / "bad", data=b"PRIVATE malformed")
    assert cli(["--storage", str(installer.storage_root), "list"]) == 1
    output = capsys.readouterr()
    assert "valid" in output.out and "Rejected catalog entry" in output.err
    assert "PRIVATE" not in output.out + output.err


def test_cli_and_main_import_no_inference_ui_or_startup_in_fresh_process(tmp_path):
    source = write_skill(tmp_path / "source")
    storage = tmp_path / "storage"
    code = """
import sys
class BlockRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('app.inference', 'app.ui', 'app.startup', 'PySide6')):
            raise AssertionError('Skill management must not start UI or inference')
sys.meta_path.insert(0, BlockRuntime())
from app.main import main
sys.argv = ['orsi', 'skill', '--storage', sys.argv[1], 'install', sys.argv[2]]
raise SystemExit(main())
"""
    completed = subprocess.run([sys.executable, "-B", "-c", code, str(storage), str(source.parent)],
        cwd=REPO, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert "Installed" in completed.stdout
    assert SkillRegistry(global_root=storage).discover().skills[0].name == "frontend"


def test_portable_launcher_preserves_caller_relative_paths_and_exit_code(tmp_path):
    write_skill(tmp_path / "source with spaces")
    command = f'"{REPO / "ORSI.cmd"}" skill --storage "{tmp_path / "storage"}" install "source with spaces"'
    completed = subprocess.run(command, shell=True, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert "Installed" in completed.stdout
    registry = SkillRegistry(global_root=tmp_path / "storage")
    assert registry.discover().skills[0].name == "frontend"
    command = f'"{REPO / "ORSI.cmd"}" skill --storage "{tmp_path / "storage"}" info missing'
    completed = subprocess.run(command, shell=True, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 1 and "not_found" in completed.stderr
