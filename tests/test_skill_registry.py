"""Phase 2.2: authoritative snapshots, reload and passive application startup."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from app.runtime.skills import SkillDiscoveryReport, SkillLoadError, SkillLoadErrorCode, SkillRegistry
from app.runtime.skills import registry as registry_module


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows skill discovery")


def write_skill(scope, folder, name="frontend", body="PRIVATE-INSTRUCTIONS", metadata=""):
    root = scope / folder
    root.mkdir(parents=True, exist_ok=True)
    source = root / "SKILL.md"
    source.write_bytes(("---\nname: " + json.dumps(name) + "\ndescription: Design guidance.\n"
                        + metadata + "---\n" + body).encode("utf-8"))
    return source


def names(registry):
    return tuple(skill.name for skill in registry.list())


def test_constructor_and_cached_reads_do_not_scan(tmp_path, monkeypatch):
    def forbidden(**_kwargs):
        pytest.fail("Only discover/reload may read skill directories")

    monkeypatch.setattr(registry_module, "discover_skills", forbidden)
    registry = SkillRegistry(global_root=tmp_path / "absent")
    assert registry.report == SkillDiscoveryReport()
    assert registry.list() == () and registry.get("missing") is None
    assert not (tmp_path / "absent").exists()


def test_discover_registers_exact_definition_and_sorted_effective_set(tmp_path):
    root = tmp_path / "global"
    source = write_skill(root, "first", "sql", "# SQL 🔎\r\nExact body.\r\n", "optional: [one, two]\n")
    write_skill(root, "last", "frontend")
    registry = SkillRegistry(global_root=root)
    report = registry.discover()
    assert names(registry) == ("frontend", "sql")
    assert report == registry.report and not report.issues
    skill = registry.get("sql")
    assert (skill.name, skill.description, skill.instructions, skill.metadata) == (
        "sql", "Design guidance.", "# SQL 🔎\r\nExact body.\r\n", {"optional": ["one", "two"]})
    assert skill.source_path == source and skill.root_path == source.parent
    assert registry.discover() == report


def test_lookup_uses_exact_name_and_missing_returns_none(tmp_path):
    write_skill(tmp_path, "valid", "Frontend")
    registry = SkillRegistry(global_root=tmp_path)
    registry.discover()
    assert registry.get("Frontend") is not None
    for missing in ("frontend", " Frontend", "Frontend ", "unknown", ""):
        assert registry.get(missing) is None


@pytest.mark.parametrize("value", [None, 1, [], Path("frontend")])
def test_invalid_lookup_name_is_rejected(value):
    with pytest.raises(TypeError, match="string name"):
        SkillRegistry().get(value)


@pytest.mark.parametrize("accessor", ["get", "list", "report", "discover", "reload"])
def test_returned_nested_metadata_cannot_mutate_catalog(tmp_path, accessor):
    write_skill(tmp_path, "valid", metadata="optional:\n  nested: [one, {two: three}]\n")
    registry = SkillRegistry(global_root=tmp_path)
    registry.discover()
    if accessor == "get":
        skill = registry.get("frontend")
    elif accessor == "list":
        skill = registry.list()[0]
    elif accessor == "report":
        skill = registry.report.skills[0]
    else:
        skill = getattr(registry, accessor)().skills[0]
    skill.metadata["optional"]["nested"][1]["two"] = "modified"
    skill.metadata["extra"] = "injected"
    assert registry.get("frontend").metadata == {"optional": {"nested": ["one", {"two": "three"}]}}


def test_loaded_reads_do_not_rescan_and_reload_replaces_removed_and_updated_skills(tmp_path, monkeypatch):
    root = tmp_path / "global"
    removed = write_skill(root, "removed", "frontend")
    updated = write_skill(root, "updated", "sql", "old")
    registry = SkillRegistry(global_root=root)
    original = registry.discover()
    removed.unlink()
    write_skill(root, "updated", "sql", "new")
    added = write_skill(root, "added", "python")

    with monkeypatch.context() as patch:
        def forbidden(**_kwargs):
            pytest.fail("Cached reads must not rescan")
        patch.setattr(registry_module, "discover_skills", forbidden)
        assert registry.report == original
        assert names(registry) == ("frontend", "sql")
        assert registry.get("sql").instructions == "old"

    report = registry.reload()
    assert not report.issues and names(registry) == ("python", "sql")
    assert registry.get("frontend") is None
    assert registry.get("sql").instructions == "new" and registry.get("sql").source_path == updated
    assert registry.get("python").source_path == added
    assert original.skills[1].instructions == "old"


def test_reload_rejects_newly_malformed_skill_without_retaining_old_body(tmp_path):
    source = write_skill(tmp_path, "valid")
    registry = SkillRegistry(global_root=tmp_path)
    registry.discover()
    source.write_bytes(b"---\nname: frontend\n---\nPRIVATE-BROKEN-CONTENT")
    report = registry.reload()
    assert registry.list() == () and registry.get("frontend") is None
    assert report.issues[0].code == "missing_field"
    assert "PRIVATE-BROKEN-CONTENT" not in report.issues[0].message
    write_skill(tmp_path, "valid", body="repaired")
    assert not registry.reload().issues
    assert registry.get("frontend").instructions == "repaired"


def test_duplicate_names_rejected_on_registration_and_reload(tmp_path):
    write_skill(tmp_path, "one")
    second = write_skill(tmp_path, "two")
    write_skill(tmp_path, "other", "sql")
    registry = SkillRegistry(global_root=tmp_path)
    report = registry.discover()
    assert names(registry) == ("sql",) and registry.get("frontend") is None
    assert len(report.issues) == 2 and all(issue.code == "duplicate_name" for issue in report.issues)
    second.unlink()
    assert not registry.reload().issues and registry.get("frontend") is not None
    write_skill(tmp_path, "two")
    assert len(registry.reload().issues) == 2 and registry.get("frontend") is None


def test_project_override_and_reload_after_removal(tmp_path, caplog):
    root = tmp_path / "global"
    project = tmp_path / "project"
    global_source = write_skill(root, "global", body="global body")
    local_source = write_skill(project / ".orsi" / "skills", "local", body="project body")
    registry = SkillRegistry(global_root=root, project_root=project)
    with caplog.at_level("INFO", logger="app.runtime.skills.discovery"):
        registry.discover()
    assert names(registry) == ("frontend",)
    assert registry.get("frontend").source_path == local_source
    assert 'name="frontend" replaces=global' in caplog.text
    assert "global body" not in caplog.text and "project body" not in caplog.text
    local_source.unlink()
    registry.reload()
    assert registry.get("frontend").source_path == global_source


def test_ambiguous_project_override_suppresses_global_in_registry(tmp_path):
    root = tmp_path / "global"
    project = tmp_path / "project"
    write_skill(root, "global")
    write_skill(project / ".orsi" / "skills", "one")
    write_skill(project / ".orsi" / "skills", "two")
    registry = SkillRegistry(global_root=root, project_root=project)
    report = registry.discover()
    assert registry.list() == () and registry.get("frontend") is None
    assert len(report.issues) == 2 and all(issue.scope == "project" for issue in report.issues)


def test_relative_roots_stay_anchored_when_cwd_changes(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    write_skill(first / "global", "one", "original")
    write_skill(second / "global", "one", "unexpected")
    write_skill(first / "project" / ".orsi" / "skills", "local", "project")
    monkeypatch.chdir(first)
    registry = SkillRegistry(global_root=Path("global"), project_root=Path("project"))
    monkeypatch.chdir(second)
    registry.discover()
    assert names(registry) == ("original", "project")
    registry.reload()
    assert names(registry) == ("original", "project")


def test_default_home_scope_is_captured_without_inferred_project(tmp_path, monkeypatch):
    first_home, other_home = tmp_path / "home", tmp_path / "other"
    write_skill(first_home / ".orsi" / "skills", "valid", "global")
    write_skill(other_home / ".orsi" / "skills", "local", "unexpected")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: first_home))
    registry = SkillRegistry()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: other_home))
    monkeypatch.chdir(other_home)
    registry.discover()
    assert names(registry) == ("global",)


@pytest.mark.parametrize("kwargs", [
    {"global_root": "global"}, {"project_root": "project"}, {"max_entries": 0},
    {"max_entries": True}, {"max_entries": 1.5}, {"max_bytes": -1}, {"max_bytes": sys.maxsize},
])
def test_invalid_registry_inputs_are_structured(kwargs):
    with pytest.raises(SkillLoadError) as caught:
        SkillRegistry(**kwargs)
    assert caught.value.code == SkillLoadErrorCode.INVALID_INPUT


@pytest.mark.parametrize("root", [Path("../outside"), Path("C:relative"), Path("bad:stream"), Path("NUL")])
def test_unsafe_roots_rejected_before_normalization(root):
    with pytest.raises(SkillLoadError) as caught:
        SkillRegistry(global_root=root)
    assert caught.value.code == SkillLoadErrorCode.UNSAFE_PATH


def test_reload_obeys_limits_and_releases_directory_and_file_handles(tmp_path):
    root = tmp_path / "global"
    source = write_skill(root, "valid")
    registry = SkillRegistry(global_root=root, max_bytes=128, max_entries=1)
    registry.discover()
    source.write_bytes(b"x" * 129)
    assert registry.reload().issues[0].code == "too_large" and registry.list() == ()
    write_skill(root, "valid")
    registry.reload()
    assert registry.get("frontend") is not None
    write_skill(root, "overflow", "sql")
    assert registry.reload().issues[0].code == "entry_limit" and registry.list() == ()
    root.rename(root.with_name("released"))
    assert registry.reload() == SkillDiscoveryReport()


def test_reload_rejects_scope_replaced_by_real_junction(tmp_path):
    import _winapi

    root = tmp_path / "global"
    outside = tmp_path / "outside"
    write_skill(root, "valid")
    write_skill(outside, "redirected", "unexpected")
    registry = SkillRegistry(global_root=root)
    registry.discover()
    root.rename(root.with_name("previous"))
    _winapi.CreateJunction(str(outside), str(root))
    assert root.is_junction()
    assert registry.reload().issues[0].code == "unsafe_path"
    assert registry.list() == ()


def test_unexpected_refresh_error_clears_stale_catalog(tmp_path, monkeypatch):
    write_skill(tmp_path, "valid")
    registry = SkillRegistry(global_root=tmp_path)
    registry.discover()

    def broken(**_kwargs):
        raise RuntimeError("unexpected scanner failure")

    monkeypatch.setattr(registry_module, "discover_skills", broken)
    with pytest.raises(RuntimeError, match="scanner failure"):
        registry.reload()
    assert registry.report == SkillDiscoveryReport() and registry.get("frontend") is None


def test_reads_wait_for_complete_refresh_snapshot(tmp_path, monkeypatch):
    write_skill(tmp_path, "valid", body="old")
    registry = SkillRegistry(global_root=tmp_path)
    registry.discover()
    write_skill(tmp_path, "valid", body="new")
    entered, release, reader_started, read_done = Event(), Event(), Event(), Event()
    actual_discover = registry_module.discover_skills
    results, failures = [], []

    def paused_scan(**kwargs):
        entered.set()
        assert release.wait(5)
        return actual_discover(**kwargs)

    def refresh():
        try:
            registry.reload()
        except BaseException as error:
            failures.append(error)

    def read():
        try:
            reader_started.set()
            results.append(registry.get("frontend"))
        except BaseException as error:
            failures.append(error)
        finally:
            read_done.set()

    monkeypatch.setattr(registry_module, "discover_skills", paused_scan)
    refresher, reader = Thread(target=refresh), Thread(target=read)
    refresher.start()
    try:
        assert entered.wait(5)
        reader.start()
        assert reader_started.wait(5)
        assert not read_done.wait(0.05)
    finally:
        release.set()
        refresher.join(5)
        if reader.ident is not None:
            reader.join(5)
    assert not refresher.is_alive() and not reader.is_alive() and not failures
    assert results[0].instructions == "new"


class RecordingInference:
    def __init__(self, **_kwargs):
        self.calls = []

    def respond(self, messages):
        self.calls.append(deepcopy(messages))
        return "reply"


def stub_inference_startup(monkeypatch, state):
    import app.startup as startup
    from app.inference.engine import InferenceUnavailable

    def no_local_model():
        raise InferenceUnavailable("test has no local model")

    monkeypatch.setattr(startup, "PATHS", SimpleNamespace(state=state))
    monkeypatch.setattr(startup, "load_model_config", no_local_model)
    monkeypatch.setattr(startup, "load_cloud_config", lambda: SimpleNamespace(default_mode="cloud", fallback_to_local=False))
    monkeypatch.setattr(startup, "OpenAICompatibleInferenceEngine", lambda _: object())
    monkeypatch.setattr(startup, "HybridInferenceEngine", RecordingInference)
    return startup


def test_application_startup_mixed_scopes_catalog_and_prompts_unchanged(tmp_path, monkeypatch):
    home, project = tmp_path / "home", tmp_path / "project"
    global_root = home / ".orsi" / "skills"
    write_skill(global_root, "design", "frontend")
    write_skill(global_root, "debug", "python")
    write_skill(global_root, "queries", "sql")
    local_root = project / ".orsi" / "skills"
    local = write_skill(local_root, "project-only", "project-guidance")
    override = write_skill(local_root, "override", "frontend", "PRIVATE-PROJECT-OVERRIDE")
    broken = write_skill(local_root, "broken", "malformed")
    broken.write_bytes(b"---\nname: malformed\n---\nPRIVATE-BROKEN-CONTENT")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    registry = SkillRegistry(project_root=project)
    startup = stub_inference_startup(monkeypatch, tmp_path / "state-populated")
    service, host, error, inference = startup.build_application(
        agent_config_override=startup.AgentFeatureConfig(), skill_registry_override=registry)
    assert error is None and host["hostname"] and service.skill_registry is registry
    assert names(service.skill_registry) == ("frontend", "project-guidance", "python", "sql")
    assert registry.get("frontend").source_path == override
    assert registry.get("project-guidance").source_path == local
    assert registry.get("malformed") is None
    assert len(registry.report.issues) == 1
    issue = registry.report.issues[0]
    assert (issue.scope, issue.source_path, issue.code) == ("project", broken, "missing_field")
    assert service.run("Help with this task") == "reply"
    service.shutdown()

    startup = stub_inference_startup(monkeypatch, tmp_path / "state-empty")
    empty_service, _, error, empty_inference = startup.build_application(
        agent_config_override=startup.AgentFeatureConfig(),
        skill_registry_override=SkillRegistry(global_root=tmp_path / "absent"))
    assert error is None and empty_service.skill_registry.list() == ()
    assert empty_service.run("Help with this task") == "reply"
    # Phase 3.2 may make one metadata-only selector call before normal answering.
    assert inference.calls[-1] == empty_inference.calls[-1]
    assert len(inference.calls) == 2 and len(empty_inference.calls) == 1
    assert "PRIVATE" not in json.dumps(inference.calls)
    empty_service.shutdown()


def test_default_application_startup_discovers_global_scope_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_skill(home / ".orsi" / "skills", "global", "global-only")
    write_skill(tmp_path / ".orsi" / "skills", "local", "unexpected")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(tmp_path)
    startup = stub_inference_startup(monkeypatch, tmp_path / "state")
    service, _, error, _ = startup.build_application(agent_config_override=startup.AgentFeatureConfig())
    assert error is None and names(service.skill_registry) == ("global-only",)
    service.shutdown()


def test_direct_conversation_service_has_empty_registry_without_scanning(tmp_path, monkeypatch):
    from app.conversation import ConversationService, ConversationStore

    def forbidden(**_kwargs):
        pytest.fail("Direct service construction must not discover implicitly")

    monkeypatch.setattr(registry_module, "discover_skills", forbidden)
    service = ConversationService(RecordingInference(), ConversationStore(tmp_path / "conversation.json"))
    assert isinstance(service.skill_registry, SkillRegistry) and service.skill_registry.list() == ()
    service.shutdown()


def test_invalid_startup_and_service_registry_rejected(tmp_path):
    import app.startup as startup
    from app.conversation import ConversationService, ConversationStore

    with pytest.raises(TypeError, match="SkillRegistry"):
        startup.build_application(skill_registry_override=object())
    with pytest.raises(TypeError, match="SkillRegistry"):
        ConversationService(RecordingInference(), ConversationStore(tmp_path / "conversation.json"), skill_registry=object())


def test_registry_has_no_inference_dependency_in_fresh_process(tmp_path):
    write_skill(tmp_path, "valid")
    code = """
import sys
class BlockInference:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'app.inference' or fullname.startswith('app.inference.'):
            raise AssertionError('Registry must not import inference')
sys.meta_path.insert(0, BlockInference())
from pathlib import Path
from app.runtime.skills import SkillRegistry
registry = SkillRegistry(global_root=Path(sys.argv[1]))
registry.discover()
assert registry.get('frontend') is not None
assert len(registry.list()) == 1 and not registry.reload().issues
"""
    completed = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                               cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
