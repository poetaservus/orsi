"""Fresh startup waits for explicit profile creation without reading legacy data."""
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from app.ui.personal_profile import ProfileChoice
from app.ui.profile_application import ProfileApplication
from tests.test_vault_controls import PASSWORD, build_synthetic, qt


def buttons(page):
    return [button.text() for button in page.findChildren(QPushButton) if button.isVisible()]


def close_controller(qt, controller):
    controller.shutdown()
    controller.window.close()
    qt.removeEventFilter(controller)


def open_creation(qt, controller, respond):
    def handle_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ProfileChoice)
        respond(dialog)
    qt.processEvents()
    QTimer.singleShot(0, handle_dialog)
    QTest.mouseClick(controller.window.personal_profile_page.create_profile, Qt.MouseButton.LeftButton)
    qt.processEvents()


def complete(dialog, location, mode="local"):
    dialog.mode.setCurrentIndex(0 if mode == "local" else 1)
    dialog.location.setText(str(location))
    dialog.password.setText(PASSWORD.decode())
    dialog.repeat.setText(PASSWORD.decode())
    dialog._accept()


def test_first_launch_only_offers_create_and_preserves_legacy_data(qt, tmp_path):
    legacy = tmp_path / "state/ui_preferences_v1.json"
    legacy.parent.mkdir()
    original = b'{"greeting_message":"Synthetic existing settings","unrelated":true}'
    legacy.write_bytes(original)
    calls = []
    controller = ProfileApplication(qt, tmp_path, lambda **kwargs: calls.append(kwargs),
        legacy_logging=lambda: pytest.fail("First launch opened legacy logging"))
    try:
        controller.start()
        window = controller.window
        page = window.personal_profile_page
        assert window.login_panel.isVisible() and page.setup_required
        assert buttons(page) == ["Create profile"]
        assert not page.findChildren(QLineEdit)
        assert not window.login_panel.findChild(QLabel, "loginBrand")
        assert window.service is None and window.inference is None and window._preferences_store is None
        assert not window.composer.isEnabled() and not window._owns_legacy
        controller.activate()
        window.settings_button.click()
        assert window.login_panel.isVisible() and window.settings_panel.isHidden()
        open_creation(qt, controller, lambda dialog: dialog.reject())
        assert controller.window is window and buttons(page) == ["Create profile"]
        assert calls == [] and legacy.read_bytes() == original
        assert not controller.manager.bootstrap.path.exists()
    finally:
        close_controller(qt, controller)


@pytest.mark.parametrize("mode", ["local", "portable"])
def test_create_from_welcome_opens_only_the_selected_profile(qt, tmp_path, mode):
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, tmp_path, build)
    location = tmp_path / "profiles/created"
    try:
        controller.start()
        assert calls == []
        open_creation(qt, controller, lambda dialog: complete(dialog, location, mode))
        assert controller.manager.active and controller.manager.locator.root == location
        assert controller.manager.locator.mode == mode
        assert len(calls) == 1 and calls[0] == {"profile_session": controller.manager.session}
        assert not hasattr(controller.window, "login_panel") and not controller.window._owns_legacy
        controller.transition(controller.manager.lock)
        page = controller.window.personal_profile_page
        assert not page.setup_required and "Unlock profile" in buttons(page)
        assert buttons(page) == ["Unlock profile", "More"]
        page.more_button.click()
        assert "Restore encrypted backup…" in buttons(page)
        assert page.password.accessibleName() == "Profile password"
        assert any(label.text() == "Unlock your profile" for label in controller.window.login_panel.findChildren(QLabel))
        assert not controller.window.login_panel.findChild(QLabel, "loginBrand")
        assert len(calls) == 1
    finally:
        close_controller(qt, controller)


def test_failed_creation_stays_on_create_only_panel(qt, tmp_path):
    occupied = tmp_path / "existing"
    occupied.mkdir()
    original = occupied / "preserve.txt"
    original.write_bytes(b"Existing files must remain untouched")
    calls = []
    controller = ProfileApplication(qt, tmp_path, lambda **kwargs: calls.append(kwargs))
    try:
        controller.start()
        open_creation(qt, controller, lambda dialog: complete(dialog, occupied))
        page = controller.window.personal_profile_page
        assert controller.window.login_panel.isVisible() and page.setup_required
        assert buttons(page) == ["Create profile"] and page.status.isVisible() and page.status.text()
        assert calls == [] and not controller.manager.active
        assert original.read_bytes() == b"Existing files must remain untouched"
        assert not controller.manager.bootstrap.path.exists()
    finally:
        close_controller(qt, controller)


def test_unreadable_selection_preserves_recovery_actions(qt, tmp_path):
    selection = tmp_path / "state/profile_locator_v1.json"
    selection.parent.mkdir()
    selection.write_bytes(b"{invalid saved selection")
    calls = []
    controller = ProfileApplication(qt, tmp_path, lambda **kwargs: calls.append(kwargs))
    try:
        controller.start()
        page = controller.window.personal_profile_page
        assert controller.window.login_panel.isVisible() and not page.setup_required
        assert "Select existing…" in buttons(page) and "Restore encrypted backup…" in buttons(page)
        assert calls == [] and selection.read_bytes() == b"{invalid saved selection"
    finally:
        close_controller(qt, controller)
