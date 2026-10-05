"""Complete snapshots, bounded references, ownership, rollback and preview handoff."""
import json
import os
from pathlib import Path
import shutil

import pytest

from app.runtime.skills import SkillInstaller, SkillRegistry, SkillInstallError
from app.runtime.skills import installer as local
from app.runtime.skills.import_source import prepare_import, install_import
from app.runtime.skills.package_format import MANIFEST_NAME, MAX_REFERENCE_BYTES
from tests.test_skill_package_format_v1 import FIXTURE


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows package transactions")


def pack(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(FIXTURE, source)
    return source


def manager(tmp_path):
    return SkillInstaller(SkillRegistry(global_root=tmp_path / "storage"))


def assert_rejected(code, call):
    with pytest.raises(SkillInstallError) as error:
        call()
    assert error.value.code == code
    return error.value


def assert_clean(tmp_path, installer):
    assert installer.list() == ()
    assert not list(tmp_path.glob(".orsi-skill-stage-*"))
    assert not list(tmp_path.glob(".orsi-skill-remove-*"))
    assert not local._lock_path(installer.storage_root).exists()


def test_complete_preview_snapshot_survives_source_changes_and_releases_handles(tmp_path):
    source, installer = pack(tmp_path), manager(tmp_path)
    imported = prepare_import(str(source))
    expected = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*.md")}
    assert imported.skill_count == 1 and imported.reference_count == 2
    assert imported.total_bytes == sum(map(len, expected.values()))
    assert not installer.storage_root.exists()
    (source / "references/behavior.md").write_bytes(b"Changed after preview")
    source.rename(tmp_path / "released-source")
    assert install_import(installer, imported).installed == ("python-clamp",)
    installed = installer.info("python-clamp")
    assert local._stored_files(installed.root_path, installer.registry.max_bytes) == expected
    assert install_import(installer, imported).already_installed == ("python-clamp",)
    installer.remove("python-clamp")
    assert_clean(tmp_path, installer)
    installer.storage_root.rename(tmp_path / "released-storage")


def test_single_file_choice_keeps_reference_directory_out_of_import(tmp_path):
    source, installer = pack(tmp_path), manager(tmp_path)
    imported = prepare_import(str(source / "SKILL.md"))
    assert imported.kind == "single-file" and imported.reference_count == 0
    install_import(installer, imported)
    assert [p.name for p in installer.info("python-clamp").root_path.iterdir()] == ["SKILL.md"]
    assert_rejected(local.SkillInstallErrorCode.CONFLICT, lambda: installer.install(source))


def test_legacy_idempotence_preserves_unrelated_files_without_claiming_ownership(tmp_path):
    source, installer = pack(tmp_path), manager(tmp_path)
    imported = prepare_import(str(source / "SKILL.md"))
    install_import(installer, imported)
    root = installer.info("python-clamp").root_path
    (root / "my-notes.txt").write_bytes(b"Preserve my notes")
    assert install_import(installer, imported).already_installed == ("python-clamp",)
    assert_rejected(local.SkillInstallErrorCode.UNSUPPORTED_RESOURCES, lambda: installer.remove("python-clamp"))
    assert (root / "my-notes.txt").read_bytes() == b"Preserve my notes"


def test_reference_only_update_is_a_conflict_until_explicit_removal(tmp_path):
    source, installer = pack(tmp_path), manager(tmp_path)
    installer.install(source)
    original = (installer.info("python-clamp").root_path / "references/behavior.md").read_bytes()
    (source / "references/behavior.md").write_bytes(b"New behavior")
    assert_rejected(local.SkillInstallErrorCode.CONFLICT, lambda: installer.install(source))
    assert (installer.info("python-clamp").root_path / "references/behavior.md").read_bytes() == original
    installer.remove("python-clamp")
    installer.install(source)
    assert (installer.info("python-clamp").root_path / "references/behavior.md").read_bytes() == b"New behavior"


@pytest.mark.parametrize("change", ["unknown", "edited", "manifest"])
def test_removal_preserves_unowned_or_changed_content_before_quarantine(tmp_path, change):
    source, installer = pack(tmp_path), manager(tmp_path)
    installer.install(source)
    root = installer.info("python-clamp").root_path
    if change == "unknown":
        (root / "references/my-notes.md").write_bytes(b"Preserve my notes")
        expected = local.SkillInstallErrorCode.UNSUPPORTED_RESOURCES
    elif change == "edited":
        (root / "references/behavior.md").write_bytes(b"Preserve my changes")
        expected = local.SkillInstallErrorCode.CONFLICT
    else:
        manifest = json.loads((root / MANIFEST_NAME).read_bytes())
        manifest["files"][1]["path"] = "../outside.md"
        (root / MANIFEST_NAME).write_text(json.dumps(manifest))
        expected = local.SkillInstallErrorCode.UNSUPPORTED_RESOURCES
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert_rejected(expected, lambda: installer.remove("python-clamp"))
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert not list(tmp_path.glob(".orsi-skill-remove-*"))


@pytest.mark.parametrize("data", [b"", b"  \r\n", b"\xff", b"PRIVATE\0content", b"PRIVATE\x7fcontent"])
def test_invalid_reference_text_rejects_before_storage_creation(tmp_path, data):
    source, installer = pack(tmp_path), manager(tmp_path)
    (source / "references/behavior.md").write_bytes(data)
    error = assert_rejected(local.SkillInstallErrorCode.INVALID_PACKAGE, lambda: installer.install(source))
    assert "PRIVATE" not in str(error) and not installer.storage_root.exists()


@pytest.mark.parametrize("limit", ["file", "count", "total", "depth", "batch"])
def test_reference_limits_include_all_documents_and_reject_atomically(tmp_path, monkeypatch, limit):
    source, installer = pack(tmp_path), manager(tmp_path)
    references = source / "references"
    if limit == "file":
        (references / "behavior.md").write_bytes(b"a" * (MAX_REFERENCE_BYTES + 1))
    elif limit == "count":
        for index in range(15):
            (references / f"extra-{index}.md").write_bytes(b"extra")
    elif limit == "total":
        for index in range(5):
            (references / f"extra-{index}.md").write_bytes(b"a" * MAX_REFERENCE_BYTES)
    elif limit == "depth":
        target = references / "a/b/c/d/e"
        target.mkdir(parents=True)
        (target / "deep.md").write_bytes(b"deep")
    else:
        monkeypatch.setattr(local, "MAX_INSTALL_BYTES", (source / "SKILL.md").stat().st_size + 1)
    assert_rejected(local.SkillInstallErrorCode.LIMIT_EXCEEDED, lambda: installer.install(source))
    assert not installer.storage_root.exists()


def test_nested_markdown_and_reference_named_skill_are_data_not_new_skills(tmp_path):
    source, installer = pack(tmp_path), manager(tmp_path)
    (source / "references/examples").mkdir()
    nested = source / "references/examples/edge.md"
    nested.write_bytes(b"\xef\xbb\xbf# Edge\r\nUnicode: \xc3\xa9\r\n")
    (source / "references/SKILL.md").write_bytes(b"Not independent skill frontmatter")
    (source / "references/ignored.bin").write_bytes(b"\0unsupported")
    assert installer.install(source).installed == ("python-clamp",)
    root = installer.info("python-clamp").root_path
    assert (root / "references/examples/edge.md").read_bytes() == nested.read_bytes()
    assert (root / "references/SKILL.md").read_bytes() == b"Not independent skill frontmatter"
    assert not (root / "references/ignored.bin").exists()
    installer.remove("python-clamp")
    assert_clean(tmp_path, installer)


@pytest.mark.parametrize("location", ["root", "child"])
def test_reference_junctions_reject_without_touching_external_content(tmp_path, location):
    import _winapi
    source, installer = pack(tmp_path), manager(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "preserve.md").write_bytes(b"outside")
    if location == "root":
        for reference in (source / "references").iterdir():
            reference.unlink()
        (source / "references").rmdir()
        target = source / "references"
    else:
        target = source / "references" / "redirect"
    _winapi.CreateJunction(str(outside), str(target))
    assert_rejected(local.SkillInstallErrorCode.UNSAFE_PATH, lambda: installer.install(source))
    assert (outside / "preserve.md").read_bytes() == b"outside"
    assert not installer.storage_root.exists()


@pytest.mark.parametrize("operation", ["partial-write", "mutated-reference", "refresh"])
def test_package_rollback_handles_partial_resources_and_preserves_existing_skills(tmp_path, monkeypatch, operation):
    source, installer = pack(tmp_path), manager(tmp_path)
    from tests.test_skill_installer import write_skill
    original = write_skill(tmp_path / "original", "original")
    installer.install(original.parent)
    expected = local.SkillInstallErrorCode.IO_ERROR
    if operation == "partial-write":
        real = local._snapshot
        def fail(path, size):
            if path.name == "behavior.md" and path.parent.parent.name.startswith(".orsi-skill-stage-"):
                raise OSError("synthetic write verification failure")
            return real(path, size)
        monkeypatch.setattr(local, "_snapshot", fail)
    elif operation == "mutated-reference":
        real = local._publish
        def change(stage, destination, identity):
            (stage / "references/behavior.md").write_bytes(b"tampered")
            return real(stage, destination, identity)
        monkeypatch.setattr(local, "_publish", change)
    else:
        real, calls = installer.registry.reload, 0
        def fail_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic refresh failure")
            return real()
        monkeypatch.setattr(installer.registry, "reload", fail_once)
        expected = local.SkillInstallErrorCode.REFRESH_FAILED
    assert_rejected(expected, lambda: installer.install(source))
    assert [s.name for s in installer.list()] == ["original"]
    assert not list(tmp_path.glob(".orsi-skill-stage-*"))
    assert not local._lock_path(installer.storage_root).exists()


def test_removal_refresh_failure_restores_every_package_document(tmp_path, monkeypatch):
    source, installer = pack(tmp_path), manager(tmp_path)
    installer.install(source)
    root = installer.info("python-clamp").root_path
    before = local._stored_files(root, installer.registry.max_bytes)
    real, calls = installer.registry.reload, 0
    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic refresh failure")
        return real()
    monkeypatch.setattr(installer.registry, "reload", fail_once)
    assert_rejected(local.SkillInstallErrorCode.REFRESH_FAILED, lambda: installer.remove("python-clamp"))
    assert local._stored_files(root, installer.registry.max_bytes) == before
    assert not list(tmp_path.glob(".orsi-skill-remove-*"))


def test_rollback_preserves_an_unowned_markdown_file_added_to_the_stage(tmp_path, monkeypatch):
    source, installer = pack(tmp_path), manager(tmp_path)
    real = local._write_package
    def fail(folder, identity, package):
        real(folder, identity, package)
        (folder / "references/my-notes.md").write_bytes(b"Preserve these notes")
        raise OSError("synthetic failure")
    monkeypatch.setattr(local, "_write_package", fail)
    assert_rejected(local.SkillInstallErrorCode.ROLLBACK_FAILED, lambda: installer.install(source))
    stages = list(tmp_path.glob(".orsi-skill-stage-*"))
    assert len(stages) == 1
    assert (stages[0] / "references/my-notes.md").read_bytes() == b"Preserve these notes"
    assert (stages[0] / "SKILL.md").read_bytes() == (source / "SKILL.md").read_bytes()
    assert installer.list() == ()
    assert not local._lock_path(installer.storage_root).exists()
