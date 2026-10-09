"""Phase 4 focused synthetic controls, migration and UI; no provider or model calls."""
from hashlib import sha256
from io import BytesIO
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from app.conversation.store import ConversationStore
from app.inference.completion import CompletionText
from app.inference.hybrid import HybridInferenceEngine
from app.state.storage import JsonStore
from app.vault.attachments import VaultAttachmentStore
from app.vault.credentials import CredentialPolicy, CredentialProvider, SessionCredentialProvider
from app.vault.migration import (CATEGORIES, apply_migration, cleanup_originals, prepare_migration,
                                 prepare_credential_import, retained_originals)
from app.vault.profiles import ProfileManager, public_error
from app.vault.types import Domain, InvalidCredentials, QuotaExceeded, State, VaultError, VaultLocked
from tests.test_vault_application import Backend

PASSWORD = b"synthetic phase four password"
MARKER = "PHASE4-PRIVATE-54fd17"
SECRET = "PHASE4-SYNTHETIC-CREDENTIAL-29bd56"


@pytest.fixture
def qt():
    app = QApplication.instance() or QApplication([])
    handlers, level = logging.getLogger().handlers[:], logging.getLogger().level
    logging.getLogger().handlers = []
    yield app
    app.processEvents()
    for handler in tuple(logging.getLogger().handlers):
        handler.close()
    logging.getLogger().handlers = handlers
    logging.getLogger().setLevel(level)


@pytest.fixture(params=["local", "portable"])
def manager(tmp_path, request):
    application = tmp_path / "application"
    application.mkdir()
    owner = ProfileManager(application)
    owner.create(application / "profiles" / "selected", mode=request.param, password=PASSWORD)
    yield owner
    owner.lock()


def ciphertext(root, *, exceptions=()):
    for path in root.rglob("*"):
        if path.is_file() and path not in exceptions and path.name != ".lease":
            assert MARKER.encode() not in path.read_bytes()
            assert SECRET.encode() not in path.read_bytes()


def test_profile_setup_restart_unlock_and_minimal_bootstrap(manager):
    manager.configure(idle_lock_minutes=15, storage_guidance_dismissed=True)
    JsonStore(manager.session.path("state/ui_preferences_v1.json")).save({"greeting_message": MARKER})
    public = manager.bootstrap.path.read_bytes()
    assert b"idle" not in public and b"credential" not in public and MARKER.encode() not in public
    assert set(json.loads(public)) == {"version", "location", "relative", "mode", "encrypted", "profile_id"}
    manager.lock()
    restarted = ProfileManager(manager.application_root)
    assert not restarted.active
    with pytest.raises(InvalidCredentials):
        restarted.unlock(b"wrong")
    assert not restarted.active
    restarted.unlock(PASSWORD)
    try:
        assert restarted.settings().load()["idle_lock_minutes"] == 15
        assert not restarted.guidance()
        assert JsonStore(restarted.session.path("state/ui_preferences_v1.json")).load()["greeting_message"] == MARKER
    finally:
        restarted.lock()
    ciphertext(manager.locator.root)


def test_public_selection_failure_never_selects_legacy_data(tmp_path):
    bootstrap = tmp_path / "state/profile_locator_v1.json"
    bootstrap.parent.mkdir()
    bootstrap.write_text("{invalid")
    manager = ProfileManager(tmp_path)
    assert manager.bootstrap_error and manager.locator is None
    assert bootstrap.read_text() == "{invalid"


def test_portable_locator_follows_application_drive_relocation(manager, tmp_path):
    if manager.locator.mode != "portable":
        return
    import shutil
    original = manager.application_root
    manager.lock()
    moved = tmp_path / "different-drive" / "application"
    shutil.copytree(original, moved)
    restarted = ProfileManager(moved)
    assert restarted.locator.root == moved / "profiles/selected"
    restarted.unlock(PASSWORD)
    restarted.lock()


def test_quota_password_recovery_backup_restore_relocation_controls(manager, tmp_path):
    vault = manager.vault()
    vault.put("documents/synthetic.txt", MARKER.encode())
    usage = manager.usage()
    assert usage["personal"] == vault.usage_bytes() and usage["free"] > 0
    with pytest.raises(QuotaExceeded):
        vault.set_quota(4096 if vault.usage_bytes() > 4096 else 1)
    vault.set_quota(2 * 1024**3)
    recovery = vault.generate_recovery_key()
    vault.change_password(b"new synthetic password")
    backup = vault.backup(tmp_path / "independent-backup")
    source = vault.root
    manager.relocate(tmp_path / "relocated", mode="portable")
    assert source.exists() and backup.exists() and not manager.active
    manager.unlock(recovery_key=recovery)
    assert manager.vault().read("documents/synthetic.txt") == MARKER.encode()
    manager.vault().disable_recovery()
    manager.restore(backup, tmp_path / "restored", mode="local", recovery_key=recovery)
    assert manager.active and manager.vault().read("documents/synthetic.txt") == MARKER.encode()
    assert source.exists() and backup.exists()


def test_failed_relocation_keeps_active_source(manager, tmp_path):
    source, session = manager.locator, manager.session
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(VaultError):
        manager.relocate(existing, mode="portable")
    assert manager.active and manager.locator == source
    assert not session._active  # Writers are drained before snapshot admission.


def test_renew_revokes_old_handles_and_drains_without_reentering_password(manager):
    old = manager.session
    old.path("documents/a.txt").write_bytes(MARKER.encode())
    path = old.path("documents/a.txt")
    stream = old.open_bytes(MARKER.encode())
    events = []
    old.register(stop=lambda: events.append("stop"), drain=lambda: events.append("drain"), clear=lambda: events.append("clear"))
    manager.renew()
    assert events == ["stop", "drain", "clear"] and stream.closed
    with pytest.raises(VaultLocked):
        path.read_bytes()
    assert manager.session.path("documents/a.txt").read_bytes() == MARKER.encode()


def test_renew_failure_releases_keys_and_does_not_open_new_consumers(manager):
    old = manager.session
    unregister = old.register(drain=lambda: (_ for _ in ()).throw(RuntimeError("synthetic worker")))
    with pytest.raises(RuntimeError):
        manager.renew()
    assert not manager.active and old._vault.state == State.LOCKED and old._vault._keys is None
    unregister()


@pytest.mark.parametrize("mode", ["local", "portable"])
def test_unencrypted_profile_explicit_session_only_credentials(tmp_path, mode):
    manager = ProfileManager(tmp_path)
    manager.create(tmp_path / "plain", mode=mode, encrypted=False)
    try:
        provider = SessionCredentialProvider(manager.session)
        backend = Backend()
        provider.bind("cloud", backend)
        provider.begin("cloud")
        provider.supply("cloud", SECRET)
        assert backend.has_api_key
        with pytest.raises(ValueError):
            provider.save("cloud", SECRET, consent=True)
        with pytest.raises(ValueError):
            provider.configure("cloud", CredentialPolicy.SAVED)
        manager.lock()
        assert not backend.has_api_key
        assert SECRET.encode() not in b"".join(p.read_bytes() for p in (tmp_path / "plain").rglob("*") if p.is_file())
        manager.unlock()
        assert manager.session.storage_path("state/ui_preferences_v1.json") == tmp_path / "plain/state/ui_preferences_v1.json"
    finally:
        manager.lock()


def legacy_fixture(root):
    from app.agent.contracts import AgentRunResult, AgentRunStatus
    outcome = AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text="synthetic response",
                             steps=1, capability_calls=0, protocol_failures=0)
    (root / "state").mkdir(parents=True)
    JsonStore(root / "state/ui_preferences_v1.json").save({"greeting_message": MARKER})
    JsonStore(root / "state/capability_journal_v1.json").save({"schema_version": 1, "records": []})
    for folder in ("personality", "templates", "instructions", "documents", "memory", "context", "indexes", "drafts", "recovery"):
        (root / folder).mkdir()
        (root / folder / "personal.txt").write_text(MARKER)
    skills = root / "personal-skills/demo"
    (skills / "references").mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: phase-four-demo\ndescription: Synthetic migration skill\n---\n" + MARKER)
    (skills / "references/guide.md").write_text(MARKER)
    source = root / "external.txt"
    source.write_text(MARKER)
    store = ConversationStore(root / "state/conversation_v1/conversation.json")
    ref = store.attachment_store.import_file(source)
    from app.conversation.attachment_processing import AttachmentProcessor
    AttachmentProcessor(store.attachment_store).prepare(ref)
    turn = store.begin_turn(MARKER, attachments=(ref,))
    store.finish_turn(turn, outcome, "synthetic response")
    store.new_session(preserve_history=True)
    turn = store.begin_turn("shared", attachments=(ref,))
    store.finish_turn(turn, outcome, "shared response")
    return store, ref


def test_all_category_migration_preserves_originals_verifies_and_keeps_shared_assets(manager, tmp_path):
    root = tmp_path / "legacy"
    store, ref = legacy_fixture(root)
    originals = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    plan = prepare_migration(root, tuple(CATEGORIES), skills_root=root / "personal-skills")
    receipt = apply_migration(manager.session, plan)
    assert len(retained_originals(manager.session, receipt)) == len(plan.originals)
    assert all(p.read_bytes() == data for p, data in originals.items())
    vault = manager.vault()
    report = json.loads(vault.read(receipt))
    assert report["verified"] and set(report["categories"]) == set(CATEGORIES)
    from app.vault.skills import VaultSkillRegistry
    assert VaultSkillRegistry(manager.session).discover().skills[0].name == "phase-four-demo"
    histories = [p for p in vault.list_paths() if p.startswith("state/conversation_v1/archives/")]
    assert len(histories) == 2
    content = "state/conversation_v1/attachments/" + ref.id + "/content"
    vault.delete((histories[0],))
    assert vault.read(content) == MARKER.encode()
    vault.delete((histories[1],))
    assert content not in vault.list_paths()
    ciphertext(manager.locator.root)


def test_migration_conflict_and_changed_source_preserve_originals(manager, tmp_path):
    root = tmp_path / "legacy"
    (root / "state").mkdir(parents=True)
    source = root / "state/ui_preferences_v1.json"
    source.write_text(json.dumps({"greeting_message": MARKER}))
    target = manager.session.path("state/ui_preferences_v1.json")
    target.write_bytes(b'{"existing":"keep"}')
    plan = prepare_migration(root, ("preferences",))
    with pytest.raises(VaultError):
        apply_migration(manager.session, plan)
    assert target.read_bytes() == b'{"existing":"keep"}'
    source.write_text("{}")
    with pytest.raises(VaultError):
        apply_migration(manager.session, plan, replace=True)
    assert source.read_text() == "{}"


def test_failed_migration_is_not_complete_or_cleanup_eligible(manager, tmp_path, monkeypatch):
    root = tmp_path / "legacy"
    (root / "documents").mkdir(parents=True)
    source = root / "documents/private.txt"
    source.write_text(MARKER)
    plan = prepare_migration(root, ("documents",))
    vault = manager.vault()
    original = vault.write_batch
    def interrupted(writes, **kwargs):
        writes = tuple(writes)
        if any(w.path == "documents/private.txt" for w in writes):
            raise OSError("synthetic interrupted migration")
        return original(writes, **kwargs)
    monkeypatch.setattr(vault, "write_batch", interrupted)
    with pytest.raises(OSError):
        apply_migration(manager.session, plan)
    receipt = "migration/" + plan.identity + ".json"
    with pytest.raises(VaultError):
        cleanup_originals(manager.session, receipt, (str(source),), consent=True)
    assert source.read_text() == MARKER and "documents/private.txt" not in vault.list_paths()


def test_verified_cleanup_is_separate_selective_and_refuses_changed_originals(manager, tmp_path):
    root = tmp_path / "legacy"
    (root / "documents").mkdir(parents=True)
    a, b = root / "documents/a.txt", root / "documents/b.txt"
    a.write_text(MARKER)
    b.write_text("retain this original")
    plan = prepare_migration(root, ("documents",))
    receipt = apply_migration(manager.session, plan)
    with pytest.raises(VaultError):
        cleanup_originals(manager.session, receipt, (str(a),))
    a.write_text("changed")
    with pytest.raises(VaultError):
        cleanup_originals(manager.session, receipt, (str(a),), consent=True)
    a.write_text(MARKER)
    assert cleanup_originals(manager.session, receipt, (str(a),), consent=True) == 1
    assert not a.exists() and b.exists()
    assert manager.vault().read("documents/a.txt") == MARKER.encode()


@pytest.mark.parametrize("kind", ["api_key", "login_token", "access_token", "refresh_token"])
def test_credential_import_separate_consent_and_field_only_cleanup(manager, tmp_path, kind):
    source = tmp_path / "old-credential.json"
    source.write_text(json.dumps({kind: SECRET, "public_setting": "preserve"}))
    with pytest.raises(VaultError):
        prepare_credential_import(source, "cloud", kind)
    plan = prepare_credential_import(source, "cloud", kind, consent=True)
    receipt = apply_migration(manager.session, plan)
    assert source.exists() and SECRET in source.read_text()
    assert manager.vault().read("cloud/" + kind, domain=Domain.CREDENTIAL) == SECRET.encode()
    assert "cloud/" + kind not in manager.vault().list_paths()
    cleanup_originals(manager.session, receipt, (str(source),), consent=True)
    assert json.loads(source.read_text()) == {"public_setting": "preserve"}
    ciphertext(manager.locator.root)


def build_synthetic(**kwargs):
    session = kwargs.get("profile_session")
    if session is None:
        return None, {"hostname": "synthetic"}, None, None
    credentials = CredentialProvider(session) if session.encrypted else SessionCredentialProvider(session)
    inference = HybridInferenceEngine(local=Backend(), cloud=Backend(), credential_provider=credentials)
    from app.conversation.orchestrator import ConversationService
    from app.vault.skills import VaultSkillRegistry
    store = ConversationStore(session.storage_path("state/conversation_v1/conversation.json"))
    registry = VaultSkillRegistry(session) if session.encrypted else None
    if registry:
        registry.discover()
    service = ConversationService(inference, store, skill_registry=registry)
    service.profile_session = session
    session.register(stop=service.stop_for_profile, drain=service.drain_for_profile, clear=service.clear_for_profile)
    return service, {"hostname": "synthetic"}, None, inference


def test_locked_startup_never_composes_private_consumers_and_keyboard_unlock(qt, manager):
    from app.ui.profile_application import ProfileApplication
    root = manager.application_root
    manager.lock()
    restarted = ProfileManager(root)
    calls = []
    def builder(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, root, builder, manager=restarted)
    try:
        controller.start()
        assert calls == [] and controller.window._preferences_store is None
        login = controller.window.login_panel
        assert login.isVisible() and not controller.window.settings_panel.isVisible()
        assert "Personal profile" not in controller.window.settings_panel.section_names
        controller.window.settings_button.click()
        assert login.isVisible() and not controller.window.settings_panel.isVisible()
        # Failed authentication stays on login without composing private consumers.
        controller.window.personal_profile_page.password.setText("wrong password")
        QTest.keyClick(controller.window.personal_profile_page.password, Qt.Key.Key_Return)
        qt.processEvents()
        assert calls == [] and not restarted.active
        assert controller.window.login_panel.isVisible()
        assert controller.window.personal_profile_page.status.isVisible()
        assert not controller.window.settings_panel.isVisible()
        page = controller.window.personal_profile_page
        assert controller.window.service is None and not controller.window.send.isEnabled()
        page.password.setText(PASSWORD.decode())
        QTest.keyClick(page.password, Qt.Key.Key_Return)
        qt.processEvents()
        assert restarted.active and len(calls) == 1 and calls[0]["profile_session"] is restarted.session
        assert controller.window.service is not None
        assert not hasattr(controller.window, "login_panel")
        assert not controller.window.settings_panel.isVisible()
        assert "Personal profile" in controller.window.settings_panel.section_names
        controller.window.input.setPlainText(MARKER)
        old = controller.window
        controller.transition(restarted.lock)
        assert not restarted.active and old.input.toPlainText() == ""
        assert controller.window._preferences_store is None
        assert not controller.window.send.isEnabled()
        assert controller.window.login_panel.isVisible() and not controller.window.settings_panel.isVisible()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_idle_lock_and_guidance_dismissal_persist(qt, manager):
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        assert manager.guidance()
        page.guidance.setChecked(False)
        assert not manager.guidance()
        page.idle.setValue(5)
        manager.configure(idle_lock_minutes=5)
        controller.check_idle(now=controller.last_activity + 301)
        assert not manager.active and controller.window.service is None
        controller.transition(lambda: manager.unlock(PASSWORD))
        assert not manager.guidance() and not controller.window.personal_profile_page.guidance.isChecked()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_profile_choice_encryption_toggle_does_not_enable_credential_persistence(qt, tmp_path):
    from app.ui.personal_profile import ProfileChoice
    dialog = ProfileChoice(ProfileManager(tmp_path))
    assert dialog.policy.currentData() == CredentialPolicy.ASK
    dialog.encryption.setChecked(False)
    assert not dialog.policy.isEnabled() and not dialog.password.isEnabled()
    assert "Recommended" not in dialog.storage_info.text()
    dialog.encryption.setChecked(True)
    assert dialog.policy.currentData() == CredentialPolicy.ASK
    dialog.password.setText(PASSWORD.decode())
    dialog.repeat.setText("wrong")
    dialog._accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.reject()


def test_image_protected_save_export_and_viewer_lock_clear(qt, manager, tmp_path):
    from app.ui.main_window import MainWindow
    from app.ui.image_viewer import ImageViewer
    store = VaultAttachmentStore(manager.session.path("state/conversation_v1/attachments"))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    from PySide6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    raw = bytes(buffer.data())
    ref = store.import_bytes(raw, name="synthetic.png", draft=True)
    window = MainWindow(None, "synthetic")
    window._profile_manager = manager
    viewer = ImageViewer(store, (ref,), parent=window)
    try:
        assert viewer.save_button.text() == "Export outside vault…" and hasattr(viewer, "vault_hint")
        viewer._store_in_vault()
        owner = "imports/images/" + ref.id + ".json"
        assert owner in manager.vault().list_paths()
        assert not store.discard_draft(ref)
        assert manager.vault().retention(store.root.key + "/" + ref.id + "/metadata.json") == (False, None)
        exported = tmp_path / "explicit-export.png"
        viewer._export_original(exported)
        assert exported.read_bytes() == raw
        with pytest.raises(OSError):
            viewer._export_original(manager.locator.root / "unsafe.png")
        manager.lock()
        assert viewer.references == () and viewer.prompt.toPlainText() == ""
        assert exported.read_bytes() == raw
    finally:
        viewer.close()
        window.close()


def test_vault_failure_messages_do_not_echo_private_exception_text():
    for error in (OSError(MARKER), ValueError(SECRET), QuotaExceeded(SECRET), InvalidCredentials(SECRET)):
        assert MARKER not in public_error(error) and SECRET not in public_error(error)


def modal_action(qt, action, edit):
    failures = []
    def handle():
        dialog = qt.activeModalWidget()
        try:
            assert dialog is not None
            edit(dialog)
        except BaseException as error:
            failures.append(error)
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()
    QTimer.singleShot(0, handle)
    action()
    assert not failures, failures


def test_password_recovery_backup_restore_and_relocate_through_controls(qt, manager, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QLineEdit
    from app.ui.profile_application import ProfileApplication
    import app.ui.personal_profile as controls
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        def change(dialog):
            fields = {w.accessibleName(): w for w in dialog.findChildren(QLineEdit)}
            fields["New vault password"].setText("replacement synthetic password")
            fields["Repeat new password"].setText("replacement synthetic password")
            dialog.accept()
        modal_action(qt, page._change_password, change)
        assert "Password changed" in page.status.text()
        exported_key = tmp_path / "independent-recovery.txt"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(exported_key), ""))
        captured = []
        def recovery(dialog):
            field = next(w for w in dialog.findChildren(QLineEdit) if w.accessibleName() == "Recovery key")
            captured.append(bytes.fromhex(field.text()))
            next(b for b in dialog.findChildren(QPushButton) if b.text().startswith("Export recovery")).click()
            dialog.reject()
        modal_action(qt, page._recovery_key, recovery)
        assert bytes.fromhex(exported_key.read_text()) == captured[0]
        backup = tmp_path / "control-backup"
        monkeypatch.setattr(page, "_destination", lambda title: backup)
        page._backup()
        assert backup.is_dir() and "verified" in page.status.text()
        source = manager.locator.root
        restored = tmp_path / "control-restored"
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(backup))
        def restore(dialog):
            fields = {w.accessibleName(): w for w in dialog.findChildren(QLineEdit)}
            fields["Restore destination"].setText(str(restored))
            fields["Backup recovery key (optional)"].setText(captured[0].hex())
            dialog.accept()
        modal_action(qt, page._restore, restore)
        assert manager.active and manager.locator.root == restored and source.is_dir()
        page = controller.window.personal_profile_page
        relocated = tmp_path / "control-relocated"
        monkeypatch.setattr(controls, "choose_mode", lambda parent: ("portable", True))
        monkeypatch.setattr(controls, "confirm", lambda *a: True)
        monkeypatch.setattr(page, "_destination", lambda title: relocated)
        page._relocate()
        assert manager.locator.root == relocated and manager.locator.mode == "portable" and not manager.active
        assert source.is_dir() and restored.is_dir() and backup.is_dir()
        controller.window.personal_profile_page.recovery.setText(captured[0].hex())
        controller.window.personal_profile_page._unlock()
        assert manager.active
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_migration_rebuild_loads_preferences_and_does_not_reuse_old_consumers(qt, manager, tmp_path):
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        old = controller.window
        old.personal_profile_page.show_section("Data")
        root = tmp_path / "legacy"
        (root / "state").mkdir(parents=True)
        source = root / "state/ui_preferences_v1.json"
        source.write_text(json.dumps({"greeting_message": MARKER, "unrelated": "preserve"}))
        plan = prepare_migration(root, ("preferences",))
        controller.transition(lambda: apply_migration(manager.session, plan, replace=True), renew=True)
        assert controller.window.greeting_input.text() == MARKER and old.greeting_input.text() == ""
        assert controller.window.service is not old.service
        assert source.exists() and source.read_text().find(MARKER) >= 0
        assert "verified" in controller.window.personal_profile_page.status.text()
        page = controller.window.personal_profile_page
        assert page.tabs.tabText(page.tabs.currentIndex()) == "Data"
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_failed_profile_drain_keeps_hidden_owner_alive_for_retry(qt, manager):
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        old = controller.window
        unregister = manager.session.register(drain=lambda: (_ for _ in ()).throw(RuntimeError("synthetic drain")))
        controller.transition(manager.lock)
        qt.processEvents()
        assert not manager.active and old in controller._retired and not old.isVisible()
        assert controller.window.service is None
        unregister()
        controller.transition(manager.lock)
        assert manager.session is None
        controller.transition(lambda: manager.unlock(PASSWORD))
        assert manager.active and controller.window.service is not None
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_guidance_disabled_on_plain_profiles_and_dismissed_on_image_viewer(qt, manager):
    from app.ui.main_window import MainWindow
    from app.ui.image_viewer import ImageViewer
    from tests.test_image_generation import image_payload
    store = VaultAttachmentStore(manager.session.path("state/conversation_v1/attachments"))
    import base64
    ref = store.import_bytes(base64.b64decode(image_payload()["output"][0]["result"]), name="synthetic.png")
    manager.configure(storage_guidance_dismissed=True)
    window = MainWindow(None, "synthetic")
    window._profile_manager = manager
    viewer = ImageViewer(store, (ref,), parent=window)
    try:
        assert not hasattr(viewer, "vault_hint")
        assert viewer.save_button.text() == "Export outside vault…"
    finally:
        viewer.close()
        window.close()


@pytest.mark.parametrize("selected", [True, False])
def test_unencrypted_application_composition_uses_selected_state_and_no_environment(qt, tmp_path, monkeypatch, selected):
    import app.startup as startup
    from tests.test_openai_phase1 import config
    manager = ProfileManager(tmp_path)
    manager.create(tmp_path / "plain", encrypted=False)
    app_root = tmp_path / "application"
    app_root.mkdir()
    monkeypatch.setattr(startup, "PATHS", SimpleNamespace(root=app_root, state=app_root / "state",
        models=app_root / "models", config=app_root / "config"))
    monkeypatch.setattr(startup, "load_model_config", lambda: (_ for _ in ()).throw(RuntimeError("no synthetic local model")))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: config(default_mode="cloud"))
    seen = []
    def backend(configuration, **kwargs):
        seen.append(kwargs)
        return Backend()
    monkeypatch.setattr(startup, "OpenAIResponsesInferenceEngine", backend)
    try:
        service, _, error, inference = startup.build_application(profile_session=manager.session if selected else None,
            session_credentials=True,
            agent_config_override=startup.AgentFeatureConfig())
        assert service is not None and error is None
        assert seen[0]["api_key"] == "" and not inference.cloud_has_api_key
        assert service.store.path.is_relative_to(tmp_path / "plain" if selected else app_root / "state")
        if selected:
            assert not (app_root / "state").exists()
        assert isinstance(inference.credential_provider, SessionCredentialProvider)
        inference.prepare_cloud_credentials()
        inference.set_cloud_api_key(SECRET)
        assert inference.cloud_has_api_key
        inference.credential_provider.end(inference.connection_id)
        assert not inference.cloud_has_api_key
        assert not manager.guidance()
    finally:
        manager.lock()
        if not selected:
            inference.close()
            inference.credential_provider.session.lock()


def test_abandoned_draft_cleanup_preserves_current_composer_and_saved_assets(manager):
    store = VaultAttachmentStore(manager.session.path("state/conversation_v1/attachments"))
    abandoned = store.import_bytes(MARKER.encode(), name="abandoned.txt", draft=True)
    current = store.import_bytes(b"current draft", name="current.txt", draft=True)
    saved = store.import_bytes(b"saved", name="saved.txt", draft=True)
    store.commit_document(manager.session.path("documents/saved.json"), {"saved": True}, (saved,))
    store.retain_drafts((saved,))
    store._drafts.pop(abandoned.id)  # A previous process no longer owns this draft.
    assert manager.delete_abandoned_drafts(owned_ids=store._drafts) == 1
    paths = manager.vault().list_paths()
    assert not any(abandoned.id in p for p in paths)
    assert any(current.id in p for p in paths) and any(saved.id in p for p in paths)


def test_setup_and_selection_actions_keep_profiles_separate_and_startup_quiet(qt, tmp_path, monkeypatch):
    from app.ui.profile_application import ProfileApplication
    import app.ui.personal_profile as controls
    manager = ProfileManager(tmp_path)
    controller = ProfileApplication(qt, tmp_path, build_synthetic, manager=manager)
    locations = iter(((tmp_path / "local", "local"), (tmp_path / "portable", "portable")))
    def create(dialog):
        root, mode = next(locations)
        dialog.mode.setCurrentIndex(0 if mode == "local" else 1)
        dialog.location.setText(str(root))
        dialog.password.setText(PASSWORD.decode())
        dialog.repeat.setText(PASSWORD.decode())
        dialog._accept()
        return dialog.result()
    monkeypatch.setattr(controls.ProfileChoice, "exec", create)
    try:
        controller.start()
        assert controller.window.settings_panel.isHidden() and manager.locator is None
        controller.window.personal_profile_page._new()
        assert manager.active and manager.locator.root == tmp_path / "local"
        manager.session.path("documents/selected.txt").write_bytes(MARKER.encode())
        old = controller.window
        old.input.setPlainText(MARKER)
        controller.window.personal_profile_page._new()
        assert manager.active and manager.locator.mode == "portable" and old.input.toPlainText() == ""
        assert "documents/selected.txt" not in manager.vault().list_paths()
        def select(dialog):
            dialog.location.setText(str(tmp_path / "local"))
            dialog.password.setText(PASSWORD.decode())
            dialog._accept()
            return dialog.result()
        monkeypatch.setattr(controls.ProfileChoice, "exec", select)
        controller.window.personal_profile_page._select()
        assert manager.vault().read("documents/selected.txt") == MARKER.encode()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_import_guidance_respects_dismissal_without_saving_credentials(qt, manager, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    titles = []
    def choose(parent, title, *args, **kwargs):
        titles.append(title)
        return "", ""
    monkeypatch.setattr(QFileDialog, "getOpenFileName", choose)
    try:
        controller.start()
        controller.window.personal_profile_page._import_copy()
        assert titles[-1].startswith("Recommended:")
        manager.configure(storage_guidance_dismissed=True)
        controller.window.personal_profile_page._import_copy()
        assert not titles[-1].startswith("Recommended:")
        assert manager.vault().list_paths(domain=Domain.CREDENTIAL) == ()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


@pytest.mark.parametrize("name", ["new-backup", "../escape", ".."])
def test_destination_picker_uses_selected_parent_and_rejects_traversal(qt, tmp_path, monkeypatch, name):
    from PySide6.QtWidgets import QFileDialog, QInputDialog
    from app.ui.main_window import MainWindow
    from app.ui.personal_profile import PersonalProfilePage
    manager = ProfileManager(tmp_path)
    window = MainWindow(None, "synthetic")
    page = PersonalProfilePage(manager, window)
    # A locator supplies only the suggested parent; no profile is opened here.
    manager.locator = SimpleNamespace(root=tmp_path / "source")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (name, True))
    try:
        target = page._destination("Encrypted backup")
        assert target == (tmp_path / name if name == "new-backup" else None)
    finally:
        page.close()
        window.close()


def test_interrupted_original_cleanup_keeps_verified_copy_and_hides_missing_original(manager, tmp_path, monkeypatch):
    root = tmp_path / "legacy"
    (root / "documents").mkdir(parents=True)
    source = root / "documents/retained.txt"
    source.write_text(MARKER)
    receipt = apply_migration(manager.session, prepare_migration(root, ("documents",)))
    vault = manager.vault()
    original_put = vault.put
    def interrupted(path, *args, **kwargs):
        if path == receipt:
            raise OSError("synthetic interrupted cleanup receipt")
        return original_put(path, *args, **kwargs)
    monkeypatch.setattr(vault, "put", interrupted)
    with pytest.raises(OSError):
        cleanup_originals(manager.session, receipt, (str(source),), consent=True)
    assert not source.exists() and retained_originals(manager.session, receipt) == ()
    assert vault.read("documents/retained.txt") == MARKER.encode()


def test_original_cleanup_refuses_changed_bytes_and_shared_files(tmp_path):
    from app.vault.files import remove_verified_original
    from app.vault.types import OriginalChanged
    source = tmp_path / "original.txt"
    source.write_bytes(MARKER.encode())
    with pytest.raises(OriginalChanged):
        remove_verified_original(source, sha256(b"different").hexdigest(), 1024)
    assert source.read_bytes() == MARKER.encode()
    alias = tmp_path / "shared.txt"
    os.link(source, alias)
    with pytest.raises(OriginalChanged):
        remove_verified_original(source, sha256(MARKER.encode()).hexdigest(), 1024)
    assert source.read_bytes() == alias.read_bytes() == MARKER.encode()


@pytest.mark.skipif(os.name != "nt", reason="Windows cleanup sharing contract")
def test_original_cleanup_holds_write_and_delete_locks_while_verifying(tmp_path, monkeypatch):
    import hashlib
    from app.vault.files import remove_verified_original
    source = tmp_path / "original.txt"
    source.write_bytes(MARKER.encode())
    measured = sha256()
    attempts = []
    class CheckedHash:
        def update(self, chunk):
            with pytest.raises(OSError):
                source.write_bytes(b"concurrent replacement")
            with pytest.raises(OSError):
                source.rename(tmp_path / "replacement.txt")
            attempts.append(True)
            measured.update(chunk)
        def hexdigest(self):
            return measured.hexdigest()
    monkeypatch.setattr(hashlib, "sha256", CheckedHash)
    remove_verified_original(source, sha256(MARKER.encode()).hexdigest(), 1024)
    assert attempts and not source.exists()


def test_restore_rejects_backup_overlap_before_lock_or_directory_creation(manager, tmp_path):
    backup = manager.vault().backup(tmp_path / "backup")
    session, selected = manager.session, manager.locator
    for target in (backup, backup / "nested" / "new-profile", backup.parent):
        with pytest.raises(VaultError):
            manager.restore(backup, target, mode="portable", password=PASSWORD)
        assert manager.active and manager.session is session and manager.locator == selected
    assert backup.exists() and not (backup / "nested").exists()


def test_saved_cloud_key_after_cancelled_prompt_is_used_without_another_prompt(qt, manager, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        window = controller.window
        page = window.personal_profile_page
        page.policy.setCurrentIndex(1)
        page._policy()
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
        assert not window._ensure_cloud_ready()
        page.key.setText(SECRET)
        page.consent.setChecked(True)
        page._save_key()
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: pytest.fail("Saved key prompted again"))
        window.model_selector.setCurrentIndex(window.model_selector.findData("cloud"))
        assert window.inference.mode == "cloud"
        assert window.inference.cloud._api_key == SECRET
        page.key.setText("replacement synthetic key")
        page.consent.setChecked(True)
        page._save_key()
        assert window._ensure_cloud_ready()
        assert window.inference.cloud._api_key == "replacement synthetic key"
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_save_key_applies_selected_policy_and_survives_restart(qt, manager, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        assert page.provider.policy(page.connection) == CredentialPolicy.ASK
        page.policy.setCurrentIndex(1)  # Save also applies this explicit choice.
        page.key.setText(SECRET)
        page.consent.setChecked(True)
        page._save_key()
        assert page.provider.policy(page.connection) == CredentialPolicy.SAVED
        assert manager.settings().load()["credential_policy"] == str(CredentialPolicy.SAVED)
        assert not page.key.text() and not page.consent.isChecked()
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: pytest.fail("Saved key prompted again"))
        assert controller.window._ensure_cloud_ready()
        controller.transition(manager.lock)
        controller.transition(lambda: manager.unlock(PASSWORD))
        page = controller.window.personal_profile_page
        assert page.policy.currentData() == CredentialPolicy.SAVED
        assert controller.window._ensure_cloud_ready()
        controller.window.inference.set_mode("cloud")
        assert controller.window.inference.cloud._api_key == SECRET
        controller.window.inference.set_mode("local")
        assert not controller.window.inference.cloud_has_api_key
        assert controller.window._ensure_cloud_ready()
        assert SECRET not in page.status.text()
        ciphertext(manager.locator.root)
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_profile_tabs_keep_edits_uncommitted_and_clear_them_on_lock(qt, manager):
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        window = controller.window
        window.settings_panel.show_section("Personal profile")
        window.settings_panel.show()
        page = window.personal_profile_page
        page.show_section("Cloud access")
        qt.processEvents()
        QTest.mouseClick(page.policy.group.button(1), Qt.MouseButton.LeftButton)
        page.key.setText(SECRET)
        page.consent.setChecked(True)
        tabs = page.tabs.tabBar()
        QTest.mouseClick(tabs, Qt.MouseButton.LeftButton, pos=tabs.tabRect(2).center())
        assert page.tabs.currentIndex() == 2
        assert page.provider.policy(page.connection) == CredentialPolicy.ASK
        assert not page.provider.has_saved_api_key(page.connection)
        assert page.key.text() == SECRET and page.consent.isChecked()
        QTest.mouseClick(tabs, Qt.MouseButton.LeftButton, pos=tabs.tabRect(1).center())
        page.sections["Cloud access"].ensureWidgetVisible(page.credential_save)
        qt.processEvents()
        QTest.mouseClick(page.credential_save, Qt.MouseButton.LeftButton)
        assert page.provider.policy(page.connection) == CredentialPolicy.SAVED
        assert manager.vault().read(page.connection + "/api_key", domain=Domain.CREDENTIAL) == SECRET.encode()
        page.key.setText("unsaved replacement")
        page.consent.setChecked(True)
        QTest.mouseClick(tabs, Qt.MouseButton.LeftButton, pos=tabs.tabRect(4).center())
        QTest.mouseClick(page.lock_profile, Qt.MouseButton.LeftButton)
        assert not manager.active and controller.window.login_panel.isVisible()
        assert not page.key.text() and not page.consent.isChecked() and page.records.count() == 0
        controller.window.personal_profile_page.password.setText(PASSWORD.decode())
        QTest.keyClick(controller.window.personal_profile_page.password, Qt.Key.Key_Return)
        assert manager.vault().read(controller.window.personal_profile_page.connection + "/api_key", domain=Domain.CREDENTIAL) == SECRET.encode()
        assert not controller.window.personal_profile_page.key.text()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_save_key_with_ask_policy_keeps_prompt_and_explains_choice(qt, manager, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        page.key.setText(SECRET)
        page.consent.setChecked(True)
        page._save_key()
        assert page.provider.policy(page.connection) == CredentialPolicy.ASK
        assert manager.vault().read(page.connection + "/api_key", domain=Domain.CREDENTIAL) == SECRET.encode()
        assert "ask" in page.status.text().casefold()
        monkeypatch.setattr(controller.window, "_saved_cloud_key_choice", lambda: "manual")
        prompted = []
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (prompted.append(True) or "", False))
        assert not controller.window._ensure_cloud_ready()
        assert prompted and not controller.window.inference.cloud_has_api_key
        assert SECRET not in page.status.text()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_save_key_without_consent_leaves_policy_and_saved_credentials_unchanged(qt, manager):
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        page.policy.setCurrentIndex(1)
        page.key.setText(SECRET)
        page._save_key()
        assert page.provider.policy(page.connection) == CredentialPolicy.ASK
        assert manager.vault().list_paths(domain=Domain.CREDENTIAL) == ()
        assert not page.key.text()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


@pytest.mark.parametrize("policy", [CredentialPolicy.ASK, CredentialPolicy.SAVED])
def test_import_key_applies_selected_policy_to_renewed_session(qt, manager, tmp_path, monkeypatch, policy):
    from PySide6.QtWidgets import QFileDialog, QInputDialog
    from app.ui.profile_application import ProfileApplication
    source = tmp_path / "credential.json"
    source.write_text(json.dumps({"api_key": SECRET, "unrelated": "preserve"}))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(source), ""))
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        old_session = manager.session
        page.policy.setCurrentIndex(0 if policy == CredentialPolicy.ASK else 1)
        page.consent.setChecked(True)
        page._import_key()
        assert manager.session is not old_session and not old_session._active
        page = controller.window.personal_profile_page
        assert page.provider.policy(page.connection) == policy
        assert manager.settings().load()["credential_policy"] == str(policy)
        assert json.loads(source.read_text()) == {"api_key": SECRET, "unrelated": "preserve"}
        if policy == CredentialPolicy.SAVED:
            monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: pytest.fail("Imported saved key prompted again"))
            assert controller.window._ensure_cloud_ready()
            assert controller.window.inference.cloud._api_key == SECRET
        else:
            prompted = []
            monkeypatch.setattr(controller.window, "_saved_cloud_key_choice", lambda: "manual")
            monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (prompted.append(True) or "", False))
            assert not controller.window._ensure_cloud_ready() and prompted
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_actual_startup_connection_reuses_ui_saved_key_after_unlock(qt, manager, monkeypatch):
    import app.startup as startup
    from app.ui.profile_application import ProfileApplication
    from PySide6.QtWidgets import QInputDialog
    from tests.test_openai_phase1 import config
    configuration = config()
    root = manager.application_root
    monkeypatch.setattr(startup, "PATHS", SimpleNamespace(root=root, state=root / "state",
        models=root / "models", config=root / "config"))
    monkeypatch.setattr(startup, "load_model_config", lambda: (_ for _ in ()).throw(RuntimeError("no synthetic local model")))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: configuration)
    backends = []
    def backend(configuration, **kwargs):
        assert kwargs["api_key"] == ""
        cloud = Backend()
        backends.append(cloud)
        return cloud
    monkeypatch.setattr(startup, "OpenAIResponsesInferenceEngine", backend)
    def build(**kwargs):
        return startup.build_application(agent_config_override=startup.AgentFeatureConfig(), **kwargs)
    controller = ProfileApplication(qt, root, build, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        connection = "cloud-" + sha256((configuration.base_url + "\0" + configuration.api_key_environment).encode()).hexdigest()
        assert page.connection == connection
        page.policy.setCurrentIndex(1)
        page.key.setText(SECRET)
        page.consent.setChecked(True)
        page._save_key()
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: pytest.fail("Actual startup lost saved key"))
        assert controller.window._ensure_cloud_ready()
        assert backends[-1]._api_key == SECRET
        controller.transition(manager.lock)
        assert not backends[-1].has_api_key
        controller.transition(lambda: manager.unlock(PASSWORD))
        assert controller.window.personal_profile_page.connection == connection
        assert controller.window._ensure_cloud_ready()
        assert backends[-1]._api_key == SECRET
        assert controller.window.inference.respond([{"role": "user", "content": "synthetic test"}]) == "synthetic reply"
        assert manager.vault().read(connection + "/api_key", domain=Domain.CREDENTIAL) == SECRET.encode()
        ciphertext(manager.locator.root)
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_retired_unlock_window_cannot_reopen_from_activation(qt, manager):
    from app.ui.main_window import MainWindow
    from app.ui.profile_application import ProfileApplication
    manager.lock()
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        old = controller.window
        old.personal_profile_page.password.setText(PASSWORD.decode())
        old.personal_profile_page._unlock()
        old.notifications.open_window()  # A delayed activation must not revive it.
        assert old.notifications.closed and old._closing and not old.isVisible()
        assert [w for w in qt.topLevelWidgets() if isinstance(w, MainWindow) and w.isVisible()] == [controller.window]
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_second_unlock_signal_from_retired_page_cannot_replace_active_profile(qt, manager):
    from app.ui.profile_application import ProfileApplication
    manager.lock()
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        page.password.setText(PASSWORD.decode())
        QTest.keyClick(page.password, Qt.Key.Key_Return)
        selected, session = controller.window, manager.session
        page._unlock()  # An already queued click/Return comes from the old page.
        assert manager.active and manager.session is session and controller.window is selected
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_failed_transition_preserving_session_does_not_build_second_consumer(qt, manager):
    from app.ui.profile_application import ProfileApplication
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, manager.application_root, build, manager=manager)
    try:
        controller.start()
        old, session = controller.window, manager.session
        def rejected():
            raise VaultError("synthetic rejected action before session changes")
        controller.transition(rejected)
        assert manager.active and manager.session is session
        assert controller.window is old and len(calls) == 1
        assert controller.window.isVisible() and not getattr(controller.window, "_closing", False)
        assert controller.window.personal_profile_page.status.text()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


@pytest.mark.parametrize("choice", ["saved", "manual", "cancel"])
def test_real_cloud_unlock_identifies_saved_key_and_requires_explicit_choice(qt, manager, monkeypatch, choice):
    import app.startup as startup
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from app.ui.main_window import MainWindow
    from app.ui.profile_application import ProfileApplication
    from tests.test_openai_phase1 import config
    root, configuration = manager.application_root, config()
    connection = "cloud-" + sha256((configuration.base_url + "\0" + configuration.api_key_environment).encode()).hexdigest()
    provider = CredentialProvider(manager.session)
    provider.save(connection, SECRET, consent=True)
    provider.configure(connection, CredentialPolicy.ASK)
    JsonStore(manager.session.path("state/ui_preferences_v1.json")).save({"greeting_message": MARKER})
    manager.lock()
    restarted = ProfileManager(root)
    monkeypatch.setattr(startup, "PATHS", SimpleNamespace(root=root, state=root / "state", models=root / "models", config=root / "config"))
    monkeypatch.setattr(startup, "load_model_config", lambda: (_ for _ in ()).throw(RuntimeError("no synthetic local model")))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: configuration)
    # Keep the actual Responses backend and its PersonalPath-backed catalogs.
    # Readiness binds a key only; no chat/image/provider request is made.
    controller = ProfileApplication(qt, root, lambda **kwargs:
        startup.build_application(agent_config_override=startup.AgentFeatureConfig(), **kwargs), manager=restarted)
    manual_prompts = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (manual_prompts.append(True) or "", False))
    try:
        controller.start()
        assert controller.window.startup_greeting.text() == "Unlock your personal profile"
        assert controller.window._runtime_mode_label() == "Locked"
        page = controller.window.personal_profile_page
        page.password.setText(PASSWORD.decode())
        QTest.keyClick(page.password, Qt.Key.Key_Return)
        qt.processEvents()
        page = controller.window.personal_profile_page
        assert restarted.active and controller.window.greeting_input.text() == MARKER
        assert "saved encrypted" in page.credential_status.text()
        assert "Ask mode" in page.credential_status.text()
        assert page.provider.has_saved_api_key(connection)
        def choose():
            dialog = qt.activeModalWidget()
            assert isinstance(dialog, QMessageBox)
            assert SECRET not in dialog.text() + dialog.informativeText()
            if choice == "cancel":
                dialog.reject()
            else:
                text = "Use saved key" if choice == "saved" else "Enter a different key"
                next(b for b in dialog.buttons() if b.text() == text).click()
        QTimer.singleShot(20, choose)
        assert controller.window._ensure_cloud_ready() is (choice == "saved")
        assert bool(manual_prompts) is (choice == "manual")
        assert page.provider.policy(connection) == (CredentialPolicy.SAVED if choice == "saved" else CredentialPolicy.ASK)
        if choice == "saved":
            assert controller.window.inference.cloud._api_key == SECRET
            assert "Automatic use enabled" in page.credential_status.text()
            controller.transition(restarted.lock)
            controller.transition(lambda: restarted.unlock(PASSWORD))
            assert controller.window._ensure_cloud_ready()
            assert not manual_prompts
        else:
            assert not controller.window.inference.cloud_has_api_key
        assert [w for w in qt.topLevelWidgets() if isinstance(w, MainWindow) and w.isVisible()] == [controller.window]
        ciphertext(restarted.locator.root)
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_lock_during_saved_key_decision_cancels_old_dialog_and_key_binding(qt, manager):
    from app.ui.main_window import MainWindow
    from app.ui.profile_application import ProfileApplication
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        old = controller.window
        page = old.personal_profile_page
        page.provider.save(page.connection, SECRET, consent=True)
        QTimer.singleShot(20, lambda: controller.transition(manager.lock))
        assert not old._ensure_cloud_ready()
        assert not manager.active and controller.window is not old
        assert old._closing and not old.inference.cloud_has_api_key
        assert controller.window.service is None
        assert [w for w in qt.topLevelWidgets() if isinstance(w, MainWindow) and w.isVisible()] == [controller.window]
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)
