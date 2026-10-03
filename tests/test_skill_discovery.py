"""Phase 2.1: bounded scopes, deterministic precedence and passive discovery."""
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.runtime.skills import (
    SkillDiscoveryReport, SkillLoadError, SkillLoadErrorCode, discover_skills,
)
from app.runtime.skills import discovery


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows skill discovery")


def write_skill(scope_root, folder, name="frontend", body="Use clear spacing."):
    root = scope_root / folder
    root.mkdir(parents=True)
    source = root / "SKILL.md"
    source.write_bytes(("---\nname: " + json.dumps(name) + "\ndescription: Design guidance.\n---\n" + body).encode("utf-8"))
    return source


def test_missing_and_empty_scopes_are_empty_and_not_created(tmp_path):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    assert discover_skills(global_root=global_root, project_root=project) == SkillDiscoveryReport()
    assert not global_root.exists() and not project.exists()
    global_root.mkdir()
    (project / ".orsi" / "skills").mkdir(parents=True)
    assert discover_skills(global_root=global_root, project_root=project) == SkillDiscoveryReport()


def test_single_skill_uses_real_loader_and_preserves_definition(tmp_path):
    global_root = tmp_path / "global"
    source = write_skill(global_root, "frontend-directory", body="# Design 🎨\r\nKeep exact lines.\r\n")
    report = discover_skills(global_root=global_root)
    assert not report.issues
    assert len(report.skills) == 1
    skill = report.skills[0]
    assert (skill.name, skill.description, skill.instructions) == ("frontend", "Design guidance.", "# Design 🎨\r\nKeep exact lines.\r\n")
    assert skill.source_path == source and skill.root_path == source.parent


def test_multiple_skills_sorted_by_metadata_name_not_folder_order(tmp_path):
    global_root = tmp_path / "global"
    write_skill(global_root, "first", "sql")
    write_skill(global_root, "last", "frontend")
    write_skill(global_root, "middle", "python")
    report = discover_skills(global_root=global_root)
    assert tuple(skill.name for skill in report.skills) == ("frontend", "python", "sql")
    assert report == discover_skills(global_root=global_root)


def test_invalid_skill_is_reported_without_hiding_valid_skills(tmp_path):
    global_root = tmp_path / "global"
    good = write_skill(global_root, "valid")
    bad = write_skill(global_root, "malformed")
    bad.write_bytes(b"---\nname: invalid\n---\nPRIVATE-CONTENT")
    report = discover_skills(global_root=global_root)
    assert tuple(skill.source_path for skill in report.skills) == (good,)
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert (issue.scope, issue.code, issue.source_path) == ("global", "missing_field", bad)
    assert '"description"' in issue.message and "PRIVATE-CONTENT" not in issue.message


def test_same_scope_duplicates_reject_every_matching_definition(tmp_path):
    global_root = tmp_path / "global"
    first = write_skill(global_root, "a", "duplicate")
    second = write_skill(global_root, "b", "duplicate")
    write_skill(global_root, "c", "unique")
    report = discover_skills(global_root=global_root)
    assert tuple(skill.name for skill in report.skills) == ("unique",)
    assert tuple(issue.source_path for issue in report.issues) == (first, second)
    assert all(issue.code == "duplicate_name" for issue in report.issues)


def test_project_override_wins_and_logs_only_bounded_metadata(tmp_path, caplog):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    write_skill(global_root, "global", "frontend", "PRIVATE-GLOBAL-BODY")
    source = write_skill(project / ".orsi" / "skills", "local", "frontend", "PRIVATE-PROJECT-BODY")
    with caplog.at_level(logging.INFO, logger=discovery.__name__):
        report = discover_skills(global_root=global_root, project_root=project)
    assert not report.issues
    assert tuple(skill.source_path for skill in report.skills) == (source,)
    assert report.skills[0].instructions == "PRIVATE-PROJECT-BODY"
    assert 'name="frontend" replaces=global' in caplog.text
    assert "PRIVATE-GLOBAL-BODY" not in caplog.text and "PRIVATE-PROJECT-BODY" not in caplog.text
    assert str(source) not in caplog.text


def test_ambiguous_project_override_suppresses_matching_global_skill(tmp_path):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    write_skill(global_root, "global", "frontend")
    write_skill(global_root, "other", "sql")
    local = project / ".orsi" / "skills"
    write_skill(local, "one", "frontend")
    write_skill(local, "two", "frontend")
    report = discover_skills(global_root=global_root, project_root=project)
    assert tuple(skill.name for skill in report.skills) == ("sql",)
    assert len(report.issues) == 2
    assert all(issue.scope == "project" and issue.code == "duplicate_name" for issue in report.issues)


def test_unique_project_skill_can_replace_ambiguous_global_name(tmp_path):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    write_skill(global_root, "one", "frontend")
    write_skill(global_root, "two", "frontend")
    source = write_skill(project / ".orsi" / "skills", "local", "frontend")
    report = discover_skills(global_root=global_root, project_root=project)
    assert tuple(skill.source_path for skill in report.skills) == (source,)
    assert len(report.issues) == 2


def test_invalid_project_skill_does_not_override_valid_global_skill(tmp_path):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    source = write_skill(global_root, "good")
    write_skill(project / ".orsi" / "skills", "bad", body="")
    report = discover_skills(global_root=global_root, project_root=project)
    assert tuple(skill.source_path for skill in report.skills) == (source,)
    assert report.issues[0].code == "empty_instructions" and report.issues[0].scope == "project"


def test_exact_scopes_default_home_and_explicit_project_without_cwd_inference(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    project = tmp_path / "chosen_project"
    global_source = write_skill(home / ".orsi" / "skills", "global", "global")
    project_source = write_skill(project / ".orsi" / "skills", "project", "project")
    write_skill(cwd / ".orsi" / "skills", "unapproved", "unapproved")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(cwd)
    assert tuple(skill.source_path for skill in discover_skills().skills) == (global_source,)
    report = discover_skills(project_root=project)
    assert tuple(skill.source_path for skill in report.skills) == (global_source, project_source)


def test_unrelated_files_and_unexpected_nested_layouts_are_not_read(tmp_path, monkeypatch):
    global_root = tmp_path / "global"
    direct = write_skill(global_root, "valid")
    write_skill(global_root / "bundle", "nested", "nested")
    (global_root / "SKILL.md").write_text("Not a supported root-level package", encoding="utf-8")
    (global_root / "notes.txt").write_text("Unrelated", encoding="utf-8")
    calls = []
    original_load = discovery.load_skill

    def tracked(path, **kwargs):
        calls.append(path)
        return original_load(path, **kwargs)

    monkeypatch.setattr(discovery, "load_skill", tracked)
    report = discover_skills(global_root=global_root)
    assert not report.issues
    assert tuple(skill.source_path for skill in report.skills) == (direct,)
    assert set(calls) == {direct, global_root / "bundle" / "SKILL.md"}


def test_entry_limit_rejects_entire_scope_before_any_skill_read(tmp_path, monkeypatch):
    global_root = tmp_path / "global"
    write_skill(global_root, "one", "one")
    write_skill(global_root, "two", "two")
    monkeypatch.setattr(discovery, "load_skill", lambda *_args, **_kwargs: pytest.fail("Limited scope must not be read"))
    report = discover_skills(global_root=global_root, max_entries=1)
    assert not report.skills and report.issues[0].code == "entry_limit"
    assert report.issues[0].source_path == global_root
    global_root.rename(global_root.with_name("limit_handles_released"))


def test_entry_limit_exact_boundary_and_valid_other_scope(tmp_path):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    write_skill(global_root, "one", "one")
    write_skill(global_root, "two", "two")
    source = write_skill(project / ".orsi" / "skills", "local", "local")
    assert len(discover_skills(global_root=global_root, max_entries=2).skills) == 2
    report = discover_skills(global_root=global_root, project_root=project, max_entries=1)
    assert tuple(skill.source_path for skill in report.skills) == (source,)
    assert report.issues[0].scope == "global" and report.issues[0].code == "entry_limit"


def test_unrelated_entries_count_toward_scan_limit(tmp_path):
    global_root = tmp_path / "global"
    write_skill(global_root, "one")
    (global_root / "notes.txt").write_text("Unrelated", encoding="utf-8")
    assert discover_skills(global_root=global_root, max_entries=1).issues[0].code == "entry_limit"


def test_file_byte_limit_is_forwarded_to_real_loader(tmp_path):
    global_root = tmp_path / "global"
    source = write_skill(global_root, "oversized")
    report = discover_skills(global_root=global_root, max_bytes=1)
    assert not report.skills
    assert report.issues[0].code == "too_large" and report.issues[0].source_path == source


@pytest.mark.parametrize("root", [Path("../outside"), Path(r"\\server\share"), Path(r"C:relative")])
def test_unsafe_roots_are_reported_without_enumeration(root, monkeypatch):
    monkeypatch.setattr(discovery.os, "scandir", lambda *_args: pytest.fail("Unsafe root must not be scanned"))
    report = discover_skills(global_root=root)
    assert not report.skills and report.issues[0].code == "unsafe_path"


def test_non_directory_root_is_rejected(tmp_path):
    root = tmp_path / "not_directory"
    root.write_text("File", encoding="utf-8")
    report = discover_skills(global_root=root)
    assert not report.skills and report.issues[0].code == "invalid_root"


@pytest.mark.parametrize("location", ["root", "child"])
def test_real_junction_roots_and_children_are_rejected_before_enumeration_or_read(tmp_path, monkeypatch, location):
    import _winapi

    global_root = tmp_path / "global"
    target = tmp_path / "outside"
    write_skill(target, "outside_skill")
    global_root.mkdir()
    link = tmp_path / "redirected_root" if location == "root" else global_root / "redirected_child"
    _winapi.CreateJunction(str(target), str(link))
    assert link.is_junction()
    if location == "root":
        global_root = link
    monkeypatch.setattr(discovery, "load_skill", lambda *_args, **_kwargs: pytest.fail("Redirected content must not be read"))
    report = discover_skills(global_root=global_root)
    assert not report.skills and report.issues[0].code == "unsafe_path"


def test_scope_junction_swap_after_inspection_is_rejected(tmp_path, monkeypatch):
    import _winapi

    global_root = tmp_path / "global"
    target = tmp_path / "outside"
    write_skill(global_root, "original")
    write_skill(target, "outside")
    original_inspect = discovery._inspect_chain

    def swap_after_inspection(path, source):
        info = original_inspect(path, source)
        global_root.rename(global_root.with_name("original_global"))
        _winapi.CreateJunction(str(target), str(global_root))
        return info

    monkeypatch.setattr(discovery, "_inspect_chain", swap_after_inspection)
    report = discover_skills(global_root=global_root)
    assert not report.skills and report.issues[0].code == "io_error"


def test_scan_io_failure_is_sanitized_and_directory_handles_release(tmp_path, monkeypatch):
    global_root = tmp_path / "global"
    write_skill(global_root, "valid")

    def denied(*_args):
        raise PermissionError("PRIVATE-CONTENT")

    with monkeypatch.context() as patch:
        patch.setattr(discovery.os, "scandir", denied)
        report = discover_skills(global_root=global_root)
    assert not report.skills and report.issues[0].code == "io_error"
    assert "PRIVATE-CONTENT" not in report.issues[0].message
    global_root.rename(global_root.with_name("scan_handles_released"))


def test_override_log_escapes_controls_and_bounds_names(tmp_path, caplog):
    global_root = tmp_path / "global"
    project = tmp_path / "project"
    name = "frontend\nFORGED-EVENT" + "x" * 300
    write_skill(global_root, "global", name)
    write_skill(project / ".orsi" / "skills", "local", name)
    with caplog.at_level(logging.INFO, logger=discovery.__name__):
        report = discover_skills(global_root=global_root, project_root=project)
    assert report.skills[0].name == name
    messages = [record.getMessage() for record in caplog.records if record.name == discovery.__name__]
    assert len(messages) == 1
    assert "\n" not in messages[0] and "\\n" in messages[0]
    assert len(messages[0]) < 250 and "..." in messages[0]


@pytest.mark.parametrize("kwargs", [
    {"global_root": "global"}, {"project_root": "project"}, {"max_entries": 0},
    {"max_entries": True}, {"max_entries": 1.5}, {"max_bytes": -1}, {"max_bytes": sys.maxsize},
])
def test_invalid_api_inputs_are_structured_rejections(kwargs):
    with pytest.raises(SkillLoadError) as caught:
        discover_skills(**kwargs)
    assert caught.value.code == SkillLoadErrorCode.INVALID_INPUT


def test_discovery_has_no_inference_dependency_in_fresh_process(tmp_path):
    global_root = tmp_path / "global"
    write_skill(global_root, "valid")
    code = """
import sys
class BlockInference:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'app.inference' or fullname.startswith('app.inference.'):
            raise AssertionError('Discovery must not import inference')
sys.meta_path.insert(0, BlockInference())
from pathlib import Path
from app.runtime.skills import discover_skills
report = discover_skills(global_root=Path(sys.argv[1]))
assert len(report.skills) == 1 and not report.issues
"""
    completed = subprocess.run([sys.executable, "-B", "-c", code, str(global_root)],
                               cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
