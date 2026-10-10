"""Missing selected locations must not become password or legacy-storage failures."""
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton

from app.ui.profile_application import ProfileApplication
from app.vault import files
from app.vault.profiles import ProfileManager, public_error
from app.vault.types import ProfileNotFound, RecoveryRequired, StorageUnavailable
from tests.test_profile_onboarding import buttons, close_controller, complete, open_creation
from tests.test_vault_controls import PASSWORD, build_synthetic, qt


def selected(tmp_path, *, encrypted=True, mode="local"):
    application = tmp_path / "application"
    application.mkdir()
    manager = ProfileManager(application)
    manager.create(application / "profiles/selected", mode=mode, encrypted=encrypted,
                   password=PASSWORD if encrypted else b"")
    manager.lock()
    return manager


def button(page, title):
    return next(control for control in page.findChildren(QPushButton)
                if control.isVisible() and control.text() == title)


def click(qt, page, title):
    QTest.mouseClick(button(page, title), Qt.MouseButton.LeftButton)
    qt.processEvents()


def assert_missing(controller):
    page = controller.window.personal_profile_page
    assert controller.window.login_panel.isVisible() and not page.setup_required
    assert isinstance(page.location_error, ProfileNotFound)
    assert page.status.isVisible() and "could not be found" in page.status.text()
    assert "password" not in page.status.text().lower() and "low on free space" not in page.status.text()
    assert page.summary.text().startswith("Previous profile location\n")
    assert not any(field.isVisible() for field in page.findChildren(QLineEdit))
    assert not hasattr(page, "password") and not hasattr(page, "recovery")
    assert buttons(page) == ["Create profile", "Check location again", "Select existing…",
                             "Use current unencrypted storage", "Restore encrypted backup…"]
    assert any(label.text() == "Profile not found" for label in controller.window.login_panel.findChildren(QLabel))
    assert controller.window.service is None and not controller.window.composer.isEnabled()
    assert not controller.window._owns_legacy and not controller.manager.active
    return page


@pytest.mark.parametrize("mode", ["local", "portable"])
@pytest.mark.parametrize("encrypted", [True, False])
def test_missing_selection_startup_rechecks_and_reconnects(qt, tmp_path, mode, encrypted):
    original = selected(tmp_path, encrypted=encrypted, mode=mode)
    root = original.locator.root
    parked = root.with_name("disconnected")
    assert root.is_relative_to(tmp_path) and parked.is_relative_to(tmp_path)
    root.rename(parked)
    saved = original.bootstrap.path.read_bytes()
    copies = original.copies.store.path.read_bytes()
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, original.application_root, build,
        legacy_logging=lambda: pytest.fail("Missing profile opened legacy storage"))
    try:
        controller.start()
        page = assert_missing(controller)
        click(qt, page, "Check location again")
        page = assert_missing(controller)
        assert calls == [] and not root.exists()
        assert controller.manager.bootstrap.path.read_bytes() == saved
        assert original.copies.store.path.read_bytes() == copies
        parked.rename(root)
        click(qt, page, "Check location again")
        page = controller.window.personal_profile_page
        assert page.location_error is None and not page.status.text()
        if encrypted:
            page.password.setText("wrong password")
            QTest.keyClick(page.password, Qt.Key.Key_Return)
            page = controller.window.personal_profile_page
            assert "Check the password or recovery key" in page.status.text()
            assert page.location_error is None and calls == []
            page.password.setText(PASSWORD.decode())
        click(qt, page, "Unlock profile" if encrypted else "Open profile")
        assert controller.manager.active and controller.manager.locator.root == root
        assert len(calls) == 1 and calls[0] == {"profile_session": controller.manager.session}
        assert not hasattr(controller.window, "login_panel")
    finally:
        close_controller(qt, controller)


@pytest.mark.parametrize("mode", ["local", "portable"])
def test_deleted_profile_can_be_replaced_through_create(qt, tmp_path, mode):
    original = selected(tmp_path, mode=mode)
    root = original.locator.root
    assert root.is_relative_to(tmp_path)
    shutil.rmtree(root)
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, original.application_root, build)
    replacement = root.with_name("replacement")
    try:
        controller.start()
        assert_missing(controller)
        open_creation(qt, controller, lambda dialog: dialog.reject())
        assert_missing(controller)
        assert calls == [] and not root.exists()
        open_creation(qt, controller, lambda dialog: complete(dialog, replacement, mode))
        assert controller.manager.active and controller.manager.locator.root == replacement
        assert len(calls) == 1 and not root.exists()
    finally:
        close_controller(qt, controller)


@pytest.mark.parametrize("recovery", [False, True])
def test_profile_removed_after_login_was_shown(qt, tmp_path, recovery):
    manager = selected(tmp_path)
    controller = ProfileApplication(qt, manager.application_root,
        lambda **kwargs: pytest.fail("Missing profile composed consumers"), manager=manager)
    try:
        controller.start()
        old_page = controller.window.personal_profile_page
        root = manager.locator.root
        assert root.is_relative_to(tmp_path)
        root.rename(root.with_name("moved-after-startup"))
        old_page.password.setText(PASSWORD.decode())
        if recovery:
            old_page.recovery.setText("01" * 32)
        QTest.keyClick(old_page.recovery if recovery else old_page.password, Qt.Key.Key_Return)
        assert not old_page.password.text() and not old_page.recovery.text()
        assert_missing(controller)
        assert not root.exists()
    finally:
        close_controller(qt, controller)


@pytest.mark.parametrize("encrypted,name", [(True, "header.json"), (True, "state.bin"), (False, "profile.json")])
def test_incomplete_profile_needs_recovery(qt, tmp_path, encrypted, name):
    manager = selected(tmp_path, encrypted=encrypted)
    (manager.locator.root / name).unlink()
    preserved = {path.name: path.read_bytes() for path in manager.locator.root.iterdir() if path.is_file()}
    controller = ProfileApplication(qt, manager.application_root,
        lambda **kwargs: pytest.fail("Incomplete profile composed consumers"), manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        assert isinstance(page.location_error, RecoveryRequired)
        assert "needs recovery" in page.status.text() and "could not be found" not in page.status.text()
        assert not page.findChildren(QLineEdit) and "Restore encrypted backup…" in buttons(page)
        assert preserved == {path.name: path.read_bytes() for path in manager.locator.root.iterdir() if path.is_file()}
    finally:
        close_controller(qt, controller)


def test_permission_error_is_unavailable_without_clearing_selection(qt, tmp_path, monkeypatch):
    manager = selected(tmp_path)
    saved = manager.bootstrap.path.read_bytes()
    real_lstat = Path.lstat
    def denied(path, *args, **kwargs):
        if path == manager.locator.root:
            raise PermissionError("synthetic private error")
        return real_lstat(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", denied)
    controller = ProfileApplication(qt, manager.application_root,
        lambda **kwargs: pytest.fail("Unreadable profile composed consumers"), manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        assert isinstance(page.location_error, StorageUnavailable)
        assert "Storage is unavailable" in page.status.text() and "could not be found" not in page.status.text()
        assert "private error" not in page.status.text() and not page.findChildren(QLineEdit)
        assert manager.bootstrap.path.read_bytes() == saved
    finally:
        close_controller(qt, controller)


@pytest.mark.parametrize("encrypted", [True, False])
def test_disappearance_during_open_is_reported_as_missing(tmp_path, monkeypatch, encrypted):
    manager = selected(tmp_path, encrypted=encrypted)
    root = manager.locator.root
    saved = manager.bootstrap.path.read_bytes()
    original_read = files.read_bytes
    def disconnect(path, limit):
        if path.parent == root:
            assert root.is_relative_to(tmp_path)
            root.rename(root.with_name("disconnected-during-open"))
        return original_read(path, limit)
    monkeypatch.setattr(files, "read_bytes", disconnect)
    with pytest.raises(ProfileNotFound):
        manager.unlock(PASSWORD if encrypted else None)
    assert not manager.active and not root.exists() and manager.bootstrap.path.read_bytes() == saved


@pytest.mark.parametrize("encrypted", [True, False])
def test_present_unreadable_profile_is_not_reported_as_missing(tmp_path, monkeypatch, encrypted):
    manager = selected(tmp_path, encrypted=encrypted)
    root = manager.locator.root
    original_read = files.read_bytes
    def denied(path, limit):
        if path.parent == root:
            raise PermissionError("synthetic private error")
        return original_read(path, limit)
    monkeypatch.setattr(files, "read_bytes", denied)
    with pytest.raises(StorageUnavailable) as raised:
        manager.unlock(PASSWORD if encrypted else None)
    assert not isinstance(raised.value, ProfileNotFound) and manager.selection_error() is None
    assert root.is_dir() and not manager.active and "private error" not in public_error(raised.value)
    assert "Storage is unavailable" in public_error(raised.value)
