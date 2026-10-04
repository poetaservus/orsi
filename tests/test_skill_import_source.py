"""Single-file import boundaries and reuse of the existing install transaction."""
from email.message import Message
from io import BytesIO
import os
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError, URLError

import pytest

from app.runtime.skills import SkillInstallError, SkillInstaller, SkillParseError, SkillRegistry
from app.runtime.skills import import_source as module
from app.runtime.skills.import_source import SkillImportError, github_skill_url, prepare_import
from tests.test_skill_activation import Recorder, make_service, skill_payload, write_skill


DATA = b"---\nname: imported\ndescription: Imported guidance.\ndisable-model-invocation: true\n---\nUse concise explanations.\n"
RAW = "https://raw.githubusercontent.com/owner/repo/main/skills/imported/SKILL.md"


@pytest.mark.parametrize("url", [RAW, RAW + "?plain=1", RAW + "#L1",
    "https://github.com/owner/repo/blob/main/skills/imported/SKILL.md",
    "https://github.com/owner/repo/blob/main/skills/imported/SKILL.md?plain=1"])
def test_github_file_links_have_one_canonical_raw_destination(url):
    assert github_skill_url(url) == RAW


@pytest.mark.parametrize("url", ["http://github.com/owner/repo/blob/main/SKILL.md",
    "https://github.com/owner/repo", "https://claude.com/marketplace/plugins/frontend-design",
    "https://github.com/owner/repo/tree/main/skill/SKILL.md",
    "https://github.com@evil.example/owner/repo/blob/main/SKILL.md",
    "https://raw.githubusercontent.com.evil.example/owner/repo/main/SKILL.md",
    "https://raw.githubusercontent.com:443/owner/repo/main/SKILL.md",
    "https://github.com/owner/repo/blob/main/../SKILL.md",
    "https://github.com/owner/repo/blob/main/%2e%2e/SKILL.md",
    "https://github.com/owner/repo/blob/main/SKILL.md?token=secret",
    "https://github.com/owner/repo/blob/main/file.txt", "", "https://github.com/\nSKILL.md"])
def test_unsupported_destinations_are_rejected_without_network(url, monkeypatch):
    monkeypatch.setattr(module, "build_opener", lambda *args: pytest.fail("Network must not start"))
    with pytest.raises(SkillImportError):
        github_skill_url(url)


class Response(BytesIO):
    def __init__(self, data=DATA, *, content_type="text/plain", length=None):
        super().__init__(data)
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if length is not None:
            self.headers["Content-Length"] = length


def wire(monkeypatch, response):
    requests = []
    class Opener:
        def open(self, request, *, timeout):
            requests.append((request.full_url, timeout))
            if isinstance(response, Exception):
                raise response
            return response
    monkeypatch.setattr(module, "build_opener", lambda *args: Opener())
    return requests


def test_download_reads_only_bounded_plaintext_and_closes_response(monkeypatch):
    response = Response()
    requests = wire(monkeypatch, response)
    result = prepare_import("https://github.com/owner/repo/blob/main/skills/imported/SKILL.md?plain=1")
    assert requests == [(RAW, 10)] and response.closed
    assert result.data == DATA and result.definition.name == "imported"
    assert result.definition.metadata == {"disable-model-invocation": True}


@pytest.mark.parametrize("failure", ["announced_size", "actual_size", "html", "timeout", "utf8", "malformed"])
def test_bad_downloads_release_response_and_never_publish(monkeypatch, failure, tmp_path):
    response = Response(data=b"bad" if failure == "malformed" else b"\xff" if failure == "utf8" else DATA,
                        content_type="text/html" if failure == "html" else "text/plain",
                        length="99999" if failure == "announced_size" else None)
    wire(monkeypatch, response)
    if failure == "timeout":
        times = iter((0, 31))
        monkeypatch.setattr(module, "monotonic", lambda: next(times))
    with pytest.raises((SkillImportError, SkillParseError)):
        prepare_import(RAW, max_bytes=10 if failure == "actual_size" else 1000)
    assert response.closed and not list(tmp_path.iterdir())


@pytest.mark.parametrize("code", [301, 302, 404, 429, 500])
def test_http_errors_close_error_stream_and_expose_no_response_content(monkeypatch, code):
    stream = BytesIO(b"SECRET")
    error = HTTPError(RAW, code, "SECRET", {}, stream)
    wire(monkeypatch, error)
    with pytest.raises(SkillImportError) as caught:
        prepare_import(RAW)
    assert stream.closed and "SECRET" not in str(caught.value)


def test_connection_failure_has_safe_error(monkeypatch):
    wire(monkeypatch, URLError("PRIVATE"))
    with pytest.raises(SkillImportError) as caught:
        prepare_import(RAW)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows safe installer")
def test_reviewed_snapshot_is_installed_once_even_after_source_changes(tmp_path):
    source = tmp_path / "download.md"
    source.write_bytes(DATA)
    service, model = make_service(tmp_path)
    try:
        imported = prepare_import(str(source))
        assert service.skill_registry.get("imported") is None and not model.requests
        source.write_bytes(DATA.replace(b"concise", b"MUTATED"))
        result = service.install_skill(imported)
        assert result.installed == ("imported",)
        assert service.skill_registry.get("imported").instructions == "Use concise explanations.\n"
        assert service.install_skill(imported).already_installed == ("imported",)
        service.run("Prompt", skill_name="imported")
        assert skill_payload(model.requests[-1][0])["name"] == "imported"
        changed = prepare_import(str(source))
        with pytest.raises(SkillInstallError):
            service.install_skill(changed)
        assert "MUTATED" not in service.skill_registry.get("imported").instructions
    finally:
        service.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows safe installer")
def test_imported_preview_metadata_cannot_be_changed_before_publish(tmp_path):
    source = tmp_path / "SKILL.md"
    source.write_bytes(DATA)
    imported = prepare_import(str(source))
    imported.definition.metadata["new_hook"] = "do something"
    installer = SkillInstaller(SkillRegistry(global_root=tmp_path / "output"))
    with pytest.raises(SkillImportError):
        module.install_import(installer, imported)
    assert not installer.storage_root.exists()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows safe installer")
def test_management_is_rejected_during_turn_and_after_shutdown(tmp_path):
    started, release = Event(), Event()
    class Blocking(Recorder):
        def respond(self, messages):
            started.set()
            assert release.wait(5)
            return super().respond(messages)
    service, model = make_service(tmp_path, model=Blocking())
    service.automatic_skills_enabled = False
    source = tmp_path / "new.md"
    source.write_bytes(DATA)
    imported = prepare_import(str(source))
    thread = Thread(target=lambda: service.run("Prompt"))
    thread.start()
    assert started.wait(5)
    try:
        for operation in (lambda: service.install_skill(imported), lambda: service.remove_skill("style")):
            with pytest.raises(RuntimeError):
                operation()
        assert service.skill_registry.get("style") is not None
        assert service.skill_registry.get("imported") is None
    finally:
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        service.shutdown()
    for operation in (lambda: service.install_skill(imported), lambda: service.remove_skill("style")):
        with pytest.raises(RuntimeError):
            operation()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows safe installer")
def test_removal_clears_matching_selection_but_preserves_other_skills(tmp_path):
    service, model = make_service(tmp_path)
    try:
        service.activate_skill("style")
        service.remove_skill("style")
        assert service.active_skill is None and service.skill_registry.get("style") is None
        assert service.skill_registry.get("other") is not None and not model.requests
    finally:
        service.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows safe loader")
def test_project_override_is_read_only_for_settings_removal(tmp_path):
    global_root, project = tmp_path / "global", tmp_path / "project"
    write_skill(global_root, "style")
    source = write_skill(project / ".orsi/skills", "style")
    service, _ = make_service(tmp_path)
    service.skill_registry = SkillRegistry(global_root=global_root, project_root=project)
    service.skill_registry.discover()
    try:
        with pytest.raises(RuntimeError, match="Project skills"):
            service.remove_skill("style")
        assert source.exists() and (global_root / "style/SKILL.md").exists()
    finally:
        service.shutdown()
