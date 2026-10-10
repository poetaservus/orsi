"""Synthetic whole-profile deletion, retries and no-profile loading presentation."""
import json
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QPushButton

from app.ui.profile_application import ProfileApplication
from app.vault.engine import Vault
from app.vault.profile_cleanup import ProfileDeletionError
from app.vault.profiles import ProfileLocator, ProfileManager
from app.vault.types import Domain, VaultError, VaultLocked
from tests.test_vault_controls import PASSWORD, SECRET, build_synthetic, manager, qt


def test_deletion_removes_all_recorded_copies_domains_and_managed_backups(manager, tmp_path):
    original = manager.locator.root
    manager.vault().put("documents/private.txt", b"private document")
    manager.vault().put("connections/test/api_key", SECRET.encode(), domain=Domain.CREDENTIAL)
    manager.backup()
    external = manager.backup(tmp_path / "independent-backup")
    moved = manager.relocate(tmp_path / "moved-profile", mode="portable")
    manager.unlock(PASSWORD)
    restored = tmp_path / "restored-profile"
    manager.restore(external, restored, mode="local", password=PASSWORD)
    deleted_id = manager.locator.profile_id
    unrelated = tmp_path / "another-profile"
    manager.create(unrelated, password=PASSWORD)
    manager.vault().put("documents/keep.txt", b"unrelated profile")
    manager.select(restored, password=PASSWORD)
    manager.lock()
    restarted = ProfileManager(manager.application_root)
    restarted.unlock(PASSWORD)
    session = restarted.session
    old_path = session.path("documents/private.txt")
    stream = session.open_bytes(b"private buffer")
    keys = session._vault._keys
    phases = []
    session.register(stop=lambda: phases.append("stop"), drain=lambda: phases.append("drain"), clear=lambda: phases.append("clear"))
    assert set(restarted.deletion_targets()) == {original, external, moved, restored}
    restarted.delete_current(consent=True)
    assert phases == ["stop", "drain", "clear"] and stream.closed and not any(keys)
    with pytest.raises(VaultLocked):
        old_path.read_bytes()
    assert all(not path.exists() for path in (original, external, moved, restored))
    assert not list(tmp_path.rglob(".orsi-delete-*"))
    assert unrelated.is_dir() and not restarted.bootstrap.path.exists()
    assert not restarted.active and restarted.locator is None and not restarted.deletion_pending
    assert {item["profile_id"] for item in restarted.copies.entries()} != {deleted_id}
    assert all(item["profile_id"] != deleted_id for item in restarted.copies.entries())
    other = Vault(unrelated)
    try:
        other.unlock(PASSWORD)
        assert other.read("documents/keep.txt") == b"unrelated profile"
    finally:
        other.lock()


@pytest.mark.parametrize("mode", ["local", "portable"])
def test_plain_profile_deletion_removes_its_entire_tree(tmp_path, mode):
    manager = ProfileManager(tmp_path / "application")
    root = tmp_path / "plain-profile"
    manager.create(root, mode=mode, encrypted=False)
    (root / "documents").mkdir()
    (root / "documents/private.txt").write_bytes(b"private document")
    (root / "state/private.json").parent.mkdir(exist_ok=True)
    (root / "state/private.json").write_bytes(b'{"private":true}')
    manager.delete_current(consent=True)
    assert not root.exists() and not manager.active and manager.locator is None
    assert not manager.copies.store.path.exists() and not manager.copies.pending.path.exists()


def test_deletion_requires_confirmation_and_rejects_application_scope(manager):
    root = manager.locator.root
    with pytest.raises(VaultError):
        manager.delete_current()
    assert manager.active and root.exists() and not manager.deletion_pending
    locator = manager.locator
    manager.locator = ProfileLocator(manager.application_root, locator.mode, True, locator.profile_id)
    try:
        with pytest.raises(ProfileDeletionError):
            manager.delete_current(consent=True)
        assert root.exists() and manager.active and not manager.deletion_pending
    finally:
        manager.locator = locator


def test_busy_copy_leaves_all_files_and_can_retry_after_restart(manager, tmp_path):
    root = manager.locator.root
    copy = manager.backup(tmp_path / "busy-copy")
    other = Vault(copy)
    other.unlock(PASSWORD)
    try:
        with pytest.raises(ProfileDeletionError):
            manager.delete_current(consent=True)
        assert root.exists() and copy.exists() and manager.deletion_pending
        assert not list(tmp_path.rglob(".orsi-delete-*"))
    finally:
        other.lock()
    restarted = ProfileManager(manager.application_root)
    restarted.delete_current(consent=True)
    assert not root.exists() and not copy.exists() and not restarted.deletion_pending


def test_partial_file_failure_keeps_retry_journal_across_restart(manager, tmp_path, monkeypatch):
    manager.vault().put("documents/private.txt", b"private document")
    root = manager.locator.root
    copy = manager.backup(tmp_path / "copy")
    unlink = Path.unlink
    failed = []
    def fail_once(path, *args, **kwargs):
        if path.suffix == ".bin" and not failed:
            failed.append(True)
            raise PermissionError("synthetic locked file")
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_once)
    with pytest.raises(ProfileDeletionError):
        manager.delete_current(consent=True)
    assert manager.deletion_pending and failed
    assert len(list(tmp_path.rglob(".orsi-delete-*"))) == 2
    restarted = ProfileManager(manager.application_root)
    with pytest.raises(ProfileDeletionError):
        restarted.use_legacy()
    restarted.delete_current(consent=True)
    assert not root.exists() and not copy.exists() and not restarted.deletion_pending
    assert not list(tmp_path.rglob(".orsi-delete-*"))


def test_unavailable_or_replaced_copy_blocks_deletion_without_losing_selection(manager, tmp_path):
    parent = tmp_path / "external-location"
    parent.mkdir()
    copy = manager.backup(parent / "copy")
    offline = tmp_path / "disconnected-location"
    parent.rename(offline)
    try:
        with pytest.raises(ProfileDeletionError):
            manager.delete_current(consent=True)
        assert manager.active and manager.locator.root.exists() and not manager.deletion_pending
    finally:
        offline.rename(parent)
    header = copy / "header.json"
    original = header.read_bytes()
    changed = json.loads(original)
    changed["profile_id"] = "00000000-0000-4000-8000-000000000000"
    header.write_text(json.dumps(changed))
    try:
        with pytest.raises(ProfileDeletionError):
            manager.delete_current(consent=True)
        assert manager.active and copy.exists() and not manager.deletion_pending
    finally:
        header.write_bytes(original)


def test_retry_refuses_a_staged_copy_opened_by_another_instance(manager, tmp_path, monkeypatch):
    manager.vault().put("documents/private.txt", b"private document")
    remover = manager.copies._remove_contents
    def interrupt(*args):
        raise PermissionError("synthetic interruption before removal")
    monkeypatch.setattr(manager.copies, "_remove_contents", interrupt)
    with pytest.raises(ProfileDeletionError):
        manager.delete_current(consent=True)
    staged = next(tmp_path.rglob(".orsi-delete-*"))
    # A separate process could explicitly open a staged copy before a retry.
    from app.vault.files import Lease
    lease = Lease(staged, child_directories=())
    try:
        restarted = ProfileManager(manager.application_root)
        with pytest.raises(ProfileDeletionError):
            restarted.delete_current(consent=True)
        assert staged.exists() and (staged / "header.json").exists() and restarted.deletion_pending
    finally:
        lease.close()
    monkeypatch.setattr(manager.copies, "_remove_contents", remover)
    restarted.delete_current(consent=True)
    assert not staged.exists() and not restarted.deletion_pending


def test_failed_drain_does_not_delete_data_and_can_be_retried(manager):
    root = manager.locator.root
    failed = [True]
    cleared = []
    def drain():
        if failed[0]:
            raise RuntimeError("synthetic outstanding work")
    manager.session.register(drain=drain, clear=lambda: cleared.append(True))
    with pytest.raises(ProfileDeletionError):
        manager.delete_current(consent=True)
    assert root.exists() and manager.deletion_pending and not cleared
    failed[0] = False
    manager.delete_current(consent=True)
    assert not root.exists() and cleared == [True]


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction guard")
def test_profile_deletion_never_follows_a_directory_junction(manager, tmp_path):
    import _winapi
    external = tmp_path / "outside-documents"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_bytes(b"outside source must survive")
    root = manager.locator.root
    junction = root / "redirected"
    _winapi.CreateJunction(str(external), str(junction))
    try:
        with pytest.raises(VaultError):
            manager.delete_current(consent=True)
        assert root.exists() and manager.active and not manager.deletion_pending
        assert sentinel.read_bytes() == b"outside source must survive"
    finally:
        junction.rmdir()


def test_corrupt_copy_registry_is_preserved_and_blocks_deletion(manager):
    root = manager.locator.root
    manager.copies.store.path.write_bytes(b"{invalid registry")
    with pytest.raises(ProfileDeletionError):
        manager.delete_current(consent=True)
    assert root.exists() and manager.active and not manager.deletion_pending
    assert manager.copies.store.path.read_bytes() == b"{invalid registry"


def test_interrupted_deletion_has_a_retry_screen_and_clears_private_fields(qt, manager, tmp_path):
    from PySide6.QtWidgets import QLabel
    root = manager.locator.root
    copy = manager.backup(tmp_path / "open-copy")
    other = Vault(copy)
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        old = controller.window.personal_profile_page
        old.key.setText(SECRET)
        old.consent.setChecked(True)
        other.unlock(PASSWORD)
        controller.transition(lambda: manager.delete_current(consent=True))
        page = controller.window.personal_profile_page
        assert manager.deletion_pending and controller.window.login_panel.isVisible()
        assert not old.key.text() and not old.consent.isChecked()
        assert not page.findChildren(QLineEdit)
        assert any(label.text() == "Finish profile deletion" for label in controller.window.login_panel.findChildren(QLabel))
        actions = page.findChildren(QPushButton)
        assert [button.text() for button in actions] == ["Retry profile deletion"]
        locations = page.findChild(QListWidget)
        assert {locations.item(i).text() for i in range(locations.count())} == {str(root), str(copy)}
        assert root.exists() and copy.exists()
        other.lock()
        actions[0].click()
        assert not root.exists() and not copy.exists() and not manager.deletion_pending
        assert manager.profile_deleted and controller.window.login_panel.isVisible()
    finally:
        other.lock()
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_delete_menu_confirmation_cancels_then_deletes_and_returns_to_choices(qt, manager, monkeypatch, tmp_path):
    import app.ui.personal_profile as ui
    root = manager.locator.root
    # An older unregistered backup can be explicitly included in the review.
    older_copy = manager.vault().backup(tmp_path / "older-copy")
    monkeypatch.setattr(ui.QFileDialog, "getExistingDirectory", lambda *args: str(older_copy))
    accept = [False]
    def review(dialog):
        confirmation = next(field for field in dialog.findChildren(QLineEdit)
                            if field.accessibleName() == "Confirm profile deletion")
        remove = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Delete profile permanently")
        assert not remove.isEnabled()
        confirmation.setText("delete")
        assert not remove.isEnabled()
        if not accept[0]:
            dialog.reject()
            return QDialog.DialogCode.Rejected
        next(button for button in dialog.findChildren(QPushButton) if button.text() == "Include another backup or copy…").click()
        locations = dialog.findChild(QListWidget)
        assert {locations.item(i).text() for i in range(locations.count())} == {str(root), str(older_copy)}
        confirmation.setText("DELETE")
        assert remove.isEnabled()
        dialog.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", review)
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, manager.application_root, build, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        action = next(action for action in page.manage_profile.menu().actions() if action.text() == "Delete profile…")
        action.trigger()
        assert root.exists() and older_copy.exists() and manager.active and not manager.deletion_pending
        accept[0] = True
        old = controller.window
        action.trigger()
        assert not root.exists() and not older_copy.exists()
        assert not old.isVisible() and old._closing
        assert manager.profile_deleted and controller.window.login_panel.isVisible()
        assert len(calls) == 1  # No implicit opening of legacy history after deletion.
        assert not controller.window.personal_profile_page.findChildren(QLineEdit)
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


@pytest.mark.parametrize("starting_locked", [True, False])
def test_continue_without_profile_shows_splash_before_building_and_ignores_retired_clicks(qt, manager, monkeypatch, starting_locked):
    import app.ui.personal_profile as ui
    import app.ui.profile_application as owner
    root = manager.locator.root
    if starting_locked:
        manager.lock()
    events = []
    class Cover:
        def __init__(self, previous):
            self.geometry = previous.geometry()
        def present(self):
            events.append("present")
        def dismiss(self, reveal=None):
            assert reveal.isVisible() and reveal.geometry() == self.geometry
            events.append("dismiss")
        def deleteLater(self):
            events.append("dispose")
    monkeypatch.setattr(owner, "ProfileLoadingCover", Cover)
    monkeypatch.setattr(ui, "confirm", lambda *args: True)
    def build(**kwargs):
        if "profile_session" in kwargs:
            assert not events
            return build_synthetic(**kwargs)
        assert kwargs == {"session_credentials": True} and events == ["present"]
        events.append("build")
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, manager.application_root, build, manager=manager)
    try:
        controller.start()
        old = controller.window
        old.resize(760, 600)
        page = old.personal_profile_page
        page._legacy()
        assert events == ["present", "build", "dismiss", "dispose"]
        assert not hasattr(controller.window, "login_panel") and not manager.active and manager.locator is None
        assert root.exists() and not old.isVisible()
        page._legacy()
        assert events == ["present", "build", "dismiss", "dispose"]
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)
