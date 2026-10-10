"""Number fields must expose real editable text and persist the typed values."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QStyle, QStyleOptionFrame

from app.ui.personal_profile import ProfileChoice
from app.ui.profile_application import ProfileApplication
from app.vault.profiles import ProfileManager
from tests.test_vault_controls import PASSWORD, build_synthetic, manager, qt


def type_number(qt, field, value):
    editor = field.lineEdit()
    option = QStyleOptionFrame()
    editor.initStyleOption(option)
    text_area = editor.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, editor)
    assert text_area.width() >= editor.fontMetrics().horizontalAdvance(str(value)) + 4
    assert text_area.height() >= editor.fontMetrics().height()
    assert field.isEnabled() and field.isVisible()
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=field.rect().center())
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, str(value))
    QTest.keyClick(field, Qt.Key.Key_Return)
    qt.processEvents()
    assert field.value() == value and editor.text() == str(value)


def show_controls(qt, page, section, field):
    page.show_section(section)
    page.sections[section].ensureWidgetVisible(field)
    QTest.qWait(120)
    qt.processEvents()


def test_profile_numbers_are_visible_typable_saved_and_restored(qt, manager):
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        window = controller.window
        window.settings_panel.show_section("Personal profile")
        window.settings_panel.show()
        page = window.personal_profile_page

        show_controls(qt, page, "Storage", page.quota)
        type_number(qt, page.quota, 13)
        QTest.mouseClick(page.quota_save, Qt.MouseButton.LeftButton)
        assert manager.vault().quota_bytes == 13 * 1024**3

        show_controls(qt, page, "Storage", page.idle_controls)
        QTest.mouseClick(page.idle_toggle, Qt.MouseButton.LeftButton)
        type_number(qt, page.idle, 15)
        QTest.mouseClick(page.idle_save, Qt.MouseButton.LeftButton)
        assert manager.settings().load()["idle_lock_minutes"] == 15

        show_controls(qt, page, "Backups", page.retention_controls)
        type_number(qt, page.backup_count, 7)
        type_number(qt, page.backup_days, 90)
        accepted = []

        def accept_retention():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QMessageBox):
                accepted.append(True)
                dialog.button(QMessageBox.StandardButton.Yes).click()

        QTimer.singleShot(0, accept_retention)
        QTest.mouseClick(page.backup_save, Qt.MouseButton.LeftButton)
        assert accepted == [True]
        policy = manager.vault()._catalog["backup_policy"]
        assert policy == {"max_count": 7, "max_age_seconds": 90 * 86400}

        controller.transition(manager.lock)
        assert not manager.active and controller.window.login_panel.isVisible()
        login = controller.window.personal_profile_page
        login.password.setText(PASSWORD.decode())
        QTest.keyClick(login.password, Qt.Key.Key_Return)
        assert manager.active
        restored = controller.window.personal_profile_page
        assert [field.value() for field in (restored.quota, restored.idle,
            restored.backup_count, restored.backup_days)] == [13, 15, 7, 90]
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_new_profile_quota_is_visible_and_typable(qt, tmp_path):
    dialog = ProfileChoice(ProfileManager(tmp_path))
    try:
        dialog.show()
        QTest.qWait(50)
        type_number(qt, dialog.quota, 25)
    finally:
        dialog.reject()
        dialog.close()
