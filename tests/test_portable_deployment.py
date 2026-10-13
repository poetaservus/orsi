"""Deployment preserves the live source and verifies a complete relocatable copy."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.portable.deployment as deployment
from app.portable.deployment import (DeploymentError, MANIFEST, PROFILE_FOLDER, PUBLIC_FILES,
                                     PYTHON_PATHS, deploy_node, verify_node)
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.state.storage import JsonStore
from app.settings.personality import PersonalitySettings
from app.vault.profiles import ProfileManager
from app.vault.types import Domain, RecordWrite
from tests.test_vault_controls import PASSWORD

PRIVATE = b"DEPLOYMENT-SYNTHETIC-PRIVATE-c74570"
SECRET = b"DEPLOYMENT-SYNTHETIC-CREDENTIAL-524301"


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "application"
    root.mkdir()
    for name in (*PUBLIC_FILES, "app/main.py", "app/__init__.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"public application fixture\n")
    python = root / "runtime/python"
    python.mkdir(parents=True)
    for name in ("python.exe", "pythonw.exe", "python312.dll", "python312.zip"):
        (python / name).write_bytes(b"synthetic runtime")
    (python / "python312._pth").write_text("\n".join(PYTHON_PATHS) + "\n")
    for name in ("Lib/site-packages/vendor/LICENSE", "Lib/site-packages/nvidia/lib.dll",
                 "Lib/site-packages/llama_cpp/__init__.py", "Scripts/pip.exe", "__pycache__/test.pyc"):
        path = python / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic vendor dependency")
    for name in (".env", "state/unrelated.json", ".git/private", "app/private.json"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PRIVATE)
    (root / "models").mkdir()
    icon = root / "app/ui/assets/orsi.ico"
    icon.parent.mkdir(parents=True)
    icon.write_bytes((Path(__file__).resolve().parents[1] / "app/ui/assets/orsi.ico").read_bytes())
    personality = root / "app/conversation/personalities/choom-v1.0.0.txt"
    personality.parent.mkdir(parents=True)
    personality.write_bytes((Path(__file__).resolve().parents[1] / "app/conversation/personalities/choom-v1.0.0.txt").read_bytes())
    return root


@pytest.fixture
def manager(source):
    owner = ProfileManager(source)
    owner.create(source / "profiles/original", password=PASSWORD)
    yield owner
    owner.lock()


def destination(manager):
    return manager.application_root.parent / "portable node"


def preserved(manager):
    return manager.bootstrap.path.read_bytes(), manager.copies.store.path.read_bytes(), manager.locator, manager.session


def assert_preserved(manager, before):
    assert preserved(manager) == before and manager.active
    assert not list(manager.application_root.parent.glob(".orsi-node-*.partial"))


def test_complete_encrypted_profile_opens_independently_after_relocation(manager):
    root = manager.locator.root
    vault = manager.vault()
    PersonalitySettings(JsonStore(manager.session.storage_path("state/personality_selection_v1.json")),
                        session=manager.session).select("choom-v1.0.0")
    writes = [RecordWrite(name, PRIVATE + name.encode()) for name in
              ("state/ui_preferences_v1.json", "skills/package.json", "documents/report.txt",
               "state/conversation_v1/history.json", "setup/custom.json", "images/saved.png")]
    vault.write_batch(writes)
    vault.write_batch([RecordWrite("provider/saved", SECRET)], domain=Domain.CREDENTIAL)
    backup = vault.backup()
    new_password = b"synthetic replacement deployment password"
    vault.change_password(new_password)
    before = preserved(manager)
    source_catalog = json.loads(json.dumps(vault._catalog))
    result = deploy_node(manager, destination(manager))
    assert result.copy_registered and result.includes_profile and not result.includes_models
    assert manager.locator == before[2] and manager.session is before[3] and manager.active
    assert manager.bootstrap.path.read_bytes() == before[0]
    assert verify_node(result.destination) == result.files_verified
    assert result.destination / PROFILE_FOLDER in manager.known_roots
    assert all(str(root) not in path.read_text(errors="ignore") for path in
               (result.destination / "state").iterdir())
    for path in result.destination.rglob("*"):
        if path.is_file():
            assert PRIVATE not in path.read_bytes() and SECRET not in path.read_bytes()
    moved = result.destination.with_name("moved node")
    result.destination.rename(moved)
    copied = ProfileManager(moved)
    assert copied.locator.root == moved / PROFILE_FOLDER and copied.encrypted and not copied.active
    copied.unlock(new_password)
    try:
        assert PersonalitySettings(JsonStore(copied.session.storage_path("state/personality_selection_v1.json")),
                                   session=copied.session).current_id == "choom-v1.0.0"
        assert (moved / "app/conversation/personalities/choom-v1.0.0.txt").read_bytes() == (
            manager.application_root / "app/conversation/personalities/choom-v1.0.0.txt").read_bytes()
        assert copied.vault()._catalog["backups"] == source_catalog["backups"]
        for domain in Domain:
            assert copied.vault().list_paths(domain=domain) == vault.list_paths(domain=domain)
            for name in vault.list_paths(domain=domain):
                assert copied.vault().read(name, domain=domain) == vault.read(name, domain=domain)
        from app.vault.engine import Vault
        archived = Vault(moved / PROFILE_FOLDER / "backups" / backup.name)
        archived.unlock(PASSWORD)
        try:
            assert archived.read("documents/report.txt") == PRIVATE + b"documents/report.txt"
        finally:
            archived.lock()
        assert manager.active
    finally:
        copied.lock()
    copied.unlock(new_password)
    copied.lock()


def test_plain_profile_keeps_files_skills_and_preferences(source):
    manager = ProfileManager(source)
    manager.create(source / "profiles/plain", encrypted=False)
    JsonStore(manager.session.storage_path("state/ui_preferences_v1.json")).save({"greeting_message": PRIVATE.decode()})
    PersonalitySettings(JsonStore(manager.session.storage_path("state/personality_selection_v1.json")),
                        session=manager.session).select("choom-v1.0.0")
    for name in ("skills/example/SKILL.md", "documents/report.txt", "documents/.lease"):
        path = manager.session.storage_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PRIVATE)
    try:
        result = deploy_node(manager, destination(manager))
        copied = ProfileManager(result.destination)
        copied.unlock()
        try:
            assert copied.session.storage_path("documents/report.txt").read_bytes() == PRIVATE
            assert copied.session.storage_path("documents/.lease").read_bytes() == PRIVATE
            assert copied.session.storage_path("skills/example/SKILL.md").read_bytes() == PRIVATE
            assert JsonStore(copied.session.storage_path("state/ui_preferences_v1.json")).load()["greeting_message"] == PRIVATE.decode()
            assert PersonalitySettings(JsonStore(copied.session.storage_path("state/personality_selection_v1.json")),
                                       session=copied.session).current_id == "choom-v1.0.0"
            assert not copied.encrypted and manager.active
        finally:
            copied.lock()
    finally:
        manager.lock()


@pytest.mark.parametrize("models", [False, True])
def test_fresh_node_has_no_profile_or_instance_state(manager, models):
    if models:
        for name in ("models/model.gguf", "models/mmproj-model.gguf", "runtime/llama-server/llama-server.exe", "runtime/llama-server/ggml.dll", "runtime/llama-server/LICENSE"):
            path = manager.application_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic local inference resource")
    before = preserved(manager)
    result = deploy_node(manager, destination(manager), include_profile=False, include_models=models)
    assert not result.includes_profile and result.includes_models == models
    assert not (result.destination / "profiles").exists() and not list((result.destination / "state").iterdir())
    assert not (result.destination / ".git").exists() and not (result.destination / ".env").exists()
    assert not (result.destination / "app/private.json").exists()
    assert not (result.destination / "runtime/python/Scripts").exists()
    assert (result.destination / "runtime/python/Lib/site-packages/vendor/LICENSE").exists()
    assert (result.destination / "app/ui/assets/orsi.ico").read_bytes() == (manager.application_root / "app/ui/assets/orsi.ico").read_bytes()
    assert (result.destination / "app/conversation/personalities/choom-v1.0.0.txt").read_bytes() == (
        manager.application_root / "app/conversation/personalities/choom-v1.0.0.txt").read_bytes()
    assert (result.destination / "models/model.gguf").exists() == models
    assert (result.destination / "models/mmproj-model.gguf").exists() == models
    assert (result.destination / "runtime/llama-server/ggml.dll").exists() == models
    assert (result.destination / "runtime/llama-server/LICENSE").exists() == models
    assert (result.destination / "runtime/python/Lib/site-packages/nvidia").exists() == models
    assert (result.destination / "runtime/python/Lib/site-packages/llama_cpp").exists() == models
    assert all(PRIVATE not in path.read_bytes() for path in result.destination.rglob("*") if path.is_file())
    assert_preserved(manager, before)


@pytest.mark.parametrize("problem", ["existing", "inside_profile", "aliased_profile", "inside_install", "missing_parent", "invalid_runtime", "missing_application", "missing_models", "full_drive"])
def test_invalid_destination_or_inputs_preserve_source(manager, monkeypatch, problem):
    target = destination(manager)
    options = {}
    if problem == "existing":
        target.mkdir()
        (target / "preserve.txt").write_bytes(PRIVATE)
    elif problem == "inside_profile":
        target = manager.locator.root / "node"
    elif problem == "aliased_profile":
        outside = manager.application_root.parent / "outside"
        outside.mkdir()
        target = outside / ".." / manager.application_root.name / "profiles/original/node"
    elif problem == "inside_install":
        target = manager.application_root / "new-node"
    elif problem == "missing_parent":
        target = target / "missing-parent/node"
    elif problem == "invalid_runtime":
        (manager.application_root / "runtime/python/python312._pth").write_text("C:\\nonportable\\path")
    elif problem == "missing_application":
        (manager.application_root / "app/main.py").unlink()
    elif problem == "missing_models":
        options["include_models"] = True
    elif problem == "full_drive":
        monkeypatch.setattr(deployment.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    before = preserved(manager)
    with pytest.raises(DeploymentError):
        deploy_node(manager, target, **options)
    if problem == "existing":
        assert (target / "preserve.txt").read_bytes() == PRIVATE
    else:
        assert not target.exists()
    assert_preserved(manager, before)


@pytest.mark.parametrize("phase", ["Copying node…", "Copying your profile…", "Verifying node…"])
def test_cancel_removes_only_owned_partial_output(manager, phase):
    cancellation = CancellationSource()
    before = preserved(manager)
    def cancel(value, text):
        if text == phase:
            cancellation.cancel()
    with pytest.raises(TaskCancelled):
        deploy_node(manager, destination(manager), token=cancellation.token, progress=cancel)
    assert not destination(manager).exists()
    assert_preserved(manager, before)


def test_verification_failure_does_not_publish_or_change_selection(manager, monkeypatch):
    before = preserved(manager)
    verify = deployment.verify_node
    def corrupt(root, **kwargs):
        (root / "ORSI.cmd").write_bytes(b"unexpected change")
        return verify(root, **kwargs)
    monkeypatch.setattr(deployment, "verify_node", corrupt)
    with pytest.raises(DeploymentError, match="verification"):
        deploy_node(manager, destination(manager))
    assert not destination(manager).exists()
    assert_preserved(manager, before)


def test_output_created_during_deployment_is_preserved(manager):
    before = preserved(manager)
    target = destination(manager)
    def create(value, text):
        if text == "Verifying node…" and not target.exists():
            target.mkdir()
            (target / "other.txt").write_bytes(PRIVATE)
    with pytest.raises(DeploymentError, match="existing files were preserved"):
        deploy_node(manager, target, progress=create)
    assert (target / "other.txt").read_bytes() == PRIVATE
    assert_preserved(manager, before)


def test_locked_profile_is_required_only_for_including_personal_data(manager):
    manager.lock()
    with pytest.raises(DeploymentError, match="Unlock or open"):
        deploy_node(manager, destination(manager))
    result = deploy_node(manager, destination(manager), include_profile=False)
    assert not result.includes_profile and not manager.active


def test_copy_tracking_failure_reports_a_ready_node_separately(manager, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic registry write error")
    monkeypatch.setattr(manager.copies, "remember", fail)
    result = deploy_node(manager, destination(manager))
    assert not result.copy_registered and result.destination.is_dir()
    assert verify_node(result.destination) == result.files_verified and manager.active


def test_cancel_during_encrypted_verification_preserves_source(manager, monkeypatch):
    from app.vault import crypto
    before = preserved(manager)
    cancellation = CancellationSource()
    actual_read = crypto.read_object
    checks = []
    def cancel_during_read(*args, **kwargs):
        def check():
            checks.append(True)
            if len(checks) == 2:
                cancellation.cancel()
            cancellation.token.raise_if_cancelled()
        kwargs["check_cancelled"] = check
        return actual_read(*args, **kwargs)
    monkeypatch.setattr(crypto, "read_object", cancel_during_read)
    with pytest.raises(TaskCancelled):
        deploy_node(manager, destination(manager), token=cancellation.token)
    assert len(checks) == 2 and not destination(manager).exists()
    assert_preserved(manager, before)


def test_busy_managed_backup_blocks_export_without_revoking_source(manager):
    from app.vault.engine import Vault
    from app.vault.types import VaultBusy
    backup = manager.vault().backup()
    other = Vault(backup)
    other.unlock(PASSWORD)
    before = preserved(manager)
    try:
        with pytest.raises(VaultBusy):
            deploy_node(manager, destination(manager))
        assert not destination(manager).exists()
        assert_preserved(manager, before)
    finally:
        other.lock()
    assert deploy_node(manager, destination(manager)).copy_registered
