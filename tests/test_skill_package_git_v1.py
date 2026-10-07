"""Real Git package grouping, immutable previews and safe relative identifiers."""
import os

import pytest

from app.runtime.skills import git_installer as remote
from app.runtime.skills.import_source import prepare_import, install_import
from app.runtime.skills.installer import SkillInstaller, SkillRegistry, SkillInstallErrorCode as Code, _stored_files
from tests.test_skill_git_installer import (
    repository, local_transport, git, skill, reject, manager, contained_temp, URL,
)
from tests.test_skill_package_format_v1 import FIXTURE


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows Git package inspection")


def sample_files():
    return {"skills/clamp/" + p.relative_to(FIXTURE).as_posix(): p.read_bytes()
            for p in FIXTURE.rglob("*.md")}


def test_git_package_matches_local_bytes_and_releases_clone_before_preview(tmp_path, monkeypatch):
    files = sample_files()
    files["skills/clamp/references/SKILL.md"] = b"Supporting document, not another skill"
    files["skills/clamp/references/examples/edge.md"] = b"\xef\xbb\xbf# Edge\r\nUnicode: \xc3\xa9\r\n"
    files["skills/clamp/references/ignored.bin"] = b"\0unsupported"
    repo = repository(tmp_path, files)
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    def preview(skills):
        assert len(skills) == 1
        assert not list((tmp_path / "downloads").iterdir())
        assert not installer.installer.storage_root.exists()
    result = installer.install(URL, on_discovered=preview)
    assert result.installed == ("python-clamp",)
    root = installer.installer.info("python-clamp").root_path
    expected = {path[len("skills/clamp/"):]: data for path, data in files.items() if path.endswith(".md")}
    assert _stored_files(root, installer.installer.registry.max_bytes) == expected
    assert installer.install(URL).already_installed == ("python-clamp",)
    installer.installer.remove("python-clamp")
    assert installer.installer.list() == ()


def test_settings_repository_preview_pins_revision_and_never_downloads_on_install(tmp_path, monkeypatch):
    repo = repository(tmp_path, sample_files())
    original_revision = git(repo, "rev-parse", "HEAD").decode()
    original_clone = remote._Git.clone
    calls = []
    def clone(self, url, destination):
        assert url == "https://github.com/fixture/package.git"
        calls.append(url)
        self.run(["-c", "protocol.file.allow=always", "clone", "--bare", "--depth=1",
                  "--no-local", "--template=" + str(self.empty), "--", repo.as_uri(), str(destination)], 0)
    monkeypatch.setattr(remote._Git, "clone", clone)
    imported = prepare_import("https://github.com/fixture/package.git")
    assert imported.kind == "repository" and imported.revision == original_revision
    assert imported.reference_count == 2 and imported.skill_count == 1
    assert not list((tmp_path / "downloads").iterdir())
    (repo / "skills/clamp/references/behavior.md").write_bytes(b"Changed later")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Changed reference")
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "storage"))
    install_import(installer, imported)
    installed = installer.info("python-clamp")
    assert (installed.root_path / "references/behavior.md").read_bytes() == (FIXTURE / "references/behavior.md").read_bytes()
    assert len(calls) == 1
    monkeypatch.setattr(remote._Git, "clone", original_clone)


def test_local_and_git_discovery_stop_at_the_same_package_boundary(tmp_path, monkeypatch):
    import shutil
    files = {p.relative_to(FIXTURE).as_posix(): p.read_bytes() for p in FIXTURE.rglob("*.md")}
    files["nested/SKILL.md"] = skill("nested")
    repo = repository(tmp_path, files)
    local_transport(monkeypatch, repo)
    local_installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "local-storage"))
    assert local_installer.install(repo).installed == ("python-clamp",)
    remote_installer = manager(tmp_path)
    assert remote_installer.install(URL).installed == ("python-clamp",)
    local_root = local_installer.info("python-clamp").root_path
    remote_root = remote_installer.installer.info("python-clamp").root_path
    assert _stored_files(local_root, local_installer.registry.max_bytes) == _stored_files(
        remote_root, remote_installer.installer.registry.max_bytes)


@pytest.mark.parametrize("relative", [
    "references/../escape.md", "references/CON.md", "references/x:y.md",
    "references/%2e%2e.md", "references/name with spaces.md", "references/\u00e9.md",
])
def test_untrusted_reference_identifiers_never_become_local_paths(relative):
    oid = b"a" * 40
    tree = (b"100644 blob " + oid + b" 80\tSKILL.md\0" + b"100644 blob " + oid + b" 5\t"
            + relative.encode("utf-8") + b"\0")
    reject(Code.UNSAFE_REPOSITORY, lambda: remote._package_blobs(tree, 1024))


def test_case_collisions_in_reference_directories_reject_before_materialization():
    oid = b"a" * 40
    tree = b"".join(b"100644 blob " + oid + b" 5\t" + path + b"\0" for path in (
        b"SKILL.md", b"references/Examples/a.md", b"references/examples/b.md"))
    reject(Code.UNSAFE_REPOSITORY, lambda: remote._package_blobs(tree, 1024))


@pytest.mark.parametrize("limit", ["file", "count", "total", "batch"])
def test_git_reference_limits_reject_before_storage_creation(tmp_path, monkeypatch, limit):
    files = {"SKILL.md": skill()}
    if limit == "file":
        files["references/large.md"] = b"a" * (remote.MAX_REFERENCE_BYTES + 1)
    elif limit == "count":
        files.update({f"references/{index}.md": b"doc" for index in range(33)})
    elif limit == "total":
        files.update({f"references/{index}.md": b"a" * remote.MAX_REFERENCE_BYTES for index in range(5)})
    else:
        files["references/small.md"] = b"extra reference"
        monkeypatch.setattr(remote, "MAX_INSTALL_BYTES", len(skill()) + 1)
    repo = repository(tmp_path, files)
    local_transport(monkeypatch, repo)
    reject(Code.LIMIT_EXCEEDED, lambda: manager(tmp_path).install(URL))
    assert not (tmp_path / "storage").exists()


def test_git_package_accepts_32_references_and_preserves_every_document(tmp_path, monkeypatch):
    files = {"SKILL.md": skill()}
    files.update({f"references/{index}.md": f"Document {index}".encode() for index in range(32)})
    repo = repository(tmp_path, files)
    local_transport(monkeypatch, repo)
    installer = manager(tmp_path)
    assert installer.install(URL).installed == ("frontend",)
    installed = installer.installer.info("frontend")
    assert _stored_files(installed.root_path, installer.installer.registry.max_bytes) == files
    installer.installer.remove("frontend")
    assert installer.installer.list() == ()
