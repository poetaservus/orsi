"""Minimal login disclosure, theme continuity and real synthetic unlocks."""
import base64
import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QPushButton

from app.ui.profile_application import ProfileApplication
from app.vault.profiles import ProfileManager
from tests.test_profile_onboarding import buttons, close_controller
from tests.test_vault_controls import PASSWORD, build_synthetic, qt
from tests.test_ui_themes import package


def owner(tmp_path):
    root = tmp_path / "application"
    root.mkdir()
    manager = ProfileManager(root)
    manager.create(tmp_path / "profile", password=PASSWORD)
    return manager


@pytest.mark.parametrize("theme", ["original", "ocean", "conformist"])
def test_login_is_minimal_and_remembers_the_theme_after_lock_and_restart(qt, tmp_path, theme):
    manager = owner(tmp_path)
    calls = []
    def build(**kwargs):
        calls.append(kwargs)
        return build_synthetic(**kwargs)
    controller = ProfileApplication(qt, manager.application_root, build, manager=manager)
    try:
        controller.start()
        controller.window.theme_controller.select(theme)
        controller.transition(manager.lock)
        window = controller.window
        page, login = window.personal_profile_page, window.login_panel
        qt.processEvents()
        assert len(calls) == 1 and window.service is None and window._preferences_store is None
        assert window.theme_controller.current.identity == theme
        assert page.password.font().family() == window.theme_controller.current.family
        assert page.password.font().pixelSize() == 18
        assert page.unlock_button.font().pixelSize() == 16
        assert buttons(page) == ["Unlock profile", "More"]
        assert [field for field in page.findChildren(QLineEdit) if field.isVisible()] == [page.password]
        assert not page.summary.isVisible() and not page.recovery.isVisible()
        assert page.more_button.font().underline()
        assert page.unlock_button.width() < page.password.width() / 2
        assert login.height() < 370 and login.width() <= 480
        for control in (page.password, page.unlock_button, page.more_button):
            bounds = control.rect().translated(control.mapTo(login.scroll.viewport(), QPoint()))
            assert login.scroll.viewport().rect().contains(bounds)
        for switched in ("original", "conformist", theme):
            window.theme_controller.select(switched, persist=False)
            qt.processEvents()
            bounds = page.more_button.rect().translated(page.more_button.mapTo(login.scroll.viewport(), QPoint()))
            assert login.scroll.viewport().rect().contains(bounds)
        collapsed = login.height()
        page.password.setText("Preserve this draft")
        page.more_button.click()
        qt.processEvents()
        assert page.recovery.isVisible() and page.summary.isVisible()
        assert login.height() > collapsed
        assert {"New profile…", "Select existing…", "Use current unencrypted storage", "Restore encrypted backup…"} <= set(buttons(page))
        for size in ((760, 600), (1280, 900)):
            window.resize(*size)
            qt.processEvents()
            assert window.rect().contains(login.geometry())
            assert login.scroll.horizontalScrollBar().maximum() == 0
            for button in page.findChildren(QPushButton):
                if button.isVisible():
                    login.scroll.ensureWidgetVisible(button)
                    qt.processEvents()
                    bounds = button.rect().translated(button.mapTo(login.scroll.viewport(), QPoint()))
                    assert login.scroll.viewport().rect().contains(bounds)
        page.recovery.setText("01" * 32)
        page.more_button.click()
        qt.processEvents()
        assert not page.recovery.text() and page.password.text() == "Preserve this draft"
        assert buttons(page) == ["Unlock profile", "More"]
        cache = controller.login_appearance.store.path.read_bytes()
        assert json.loads(cache) == {"version": 1, "profile_id": manager.locator.profile_id, "theme_id": theme}
        assert b"Preserve this draft" not in cache
    finally:
        close_controller(qt, controller)
    restarted = ProfileApplication(qt, manager.application_root, build)
    try:
        restarted.start()
        assert restarted.window.theme_controller.current.identity == theme
        assert len(calls) == 1  # Login appearance never opens the encrypted profile.
        assert buttons(restarted.window.personal_profile_page) == ["Unlock profile", "More"]
    finally:
        close_controller(qt, restarted)


def test_more_is_keyboard_accessible_and_recovery_still_unlocks(qt, tmp_path):
    manager = owner(tmp_path)
    recovery = manager.vault().generate_recovery_key()
    manager.lock()
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        controller.window.activateWindow()
        qt.processEvents()
        page = controller.window.personal_profile_page
        page.password.setFocus()
        QTest.keyClick(page.password, Qt.Key.Key_Tab)
        assert page.unlock_button.hasFocus()
        QTest.keyClick(page.unlock_button, Qt.Key.Key_Tab)
        assert page.more_button.hasFocus()
        QTest.keyClick(page.more_button, Qt.Key.Key_Space)
        QTest.keyClick(page.more_button, Qt.Key.Key_Tab)
        assert page.recovery.hasFocus() and page.recovery.isVisible()
        page.recovery.setText(recovery.hex())
        QTest.keyClick(page.recovery, Qt.Key.Key_Return)
        qt.processEvents()
        assert manager.active and not hasattr(controller.window, "login_panel")
        assert not page.password.text() and not page.recovery.text()
    finally:
        close_controller(qt, controller)


def test_custom_login_colors_are_remembered_without_copying_private_assets(qt, tmp_path):
    manager = owner(tmp_path)
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    marker = "PRIVATE-THEME-ASSET-3168"
    value = package(name=marker, font={"family": "Segoe UI"},
                    palette={"settings_top": "#182121", "settings_bottom": "#182121"},
                    icons={"send": "private-icon.svg"})
    value["assets"]["private-icon.svg"] = base64.b64encode(
        ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><!--' + marker +
         '--><path d="M4 12h16" stroke="white"/></svg>').encode()).decode()
    try:
        controller.start()
        controller.window.theme_controller.repository.add(value)
        controller.window.theme_controller.select("custom")
        controller.transition(manager.lock)
        appearance = controller.window.theme_controller.current
        assert appearance.identity == "login-appearance"
        assert appearance.family == "Segoe UI" and appearance.palette["settings_top"] == "#182121"
        cached = controller.login_appearance.store.path.read_bytes()
        assert marker.encode() not in cached and b"private-icon.svg" not in cached
        assert b"assets" not in cached and b"custom" not in cached
        assert not (manager.locator.root / "state/themes/catalog_v1.json").exists()
        # A cache for a different selected profile must not override its appearance.
        controller.window.theme_controller.select("original", persist=False)
        controller.login_appearance.apply(controller.window.theme_controller, "00000000-0000-0000-0000-000000000001")
        assert controller.window.theme_controller.current.identity == "original"
    finally:
        close_controller(qt, controller)


@pytest.mark.parametrize("saved", [b"{invalid", b'{"version":1,"profile_id":1,"theme_id":"original"}',
    b'{"version":1,"profile_id":"00000000-0000-0000-0000-000000000001","theme_id":"original","overrides":{"background":1}}'])
def test_unreadable_login_appearance_is_preserved_and_does_not_block_unlock(qt, tmp_path, saved):
    manager = owner(tmp_path)
    path = manager.bootstrap.path.parent / "login_appearance_v1.json"
    path.write_bytes(saved)
    manager.lock()
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        page = controller.window.personal_profile_page
        assert controller.window.theme_controller.current.identity == "original"
        page.password.setText(PASSWORD.decode())
        QTest.keyClick(page.password, Qt.Key.Key_Return)
        qt.processEvents()
        assert manager.active and path.read_bytes() == saved
    finally:
        close_controller(qt, controller)
