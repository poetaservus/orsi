"""Essential offline language, state preservation and real profile-lifecycle gates."""
import json
import os
from unittest.mock import Mock
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel as NativeLabel, QPushButton, QStyle, QStyleOptionButton

from app.conversation.orchestrator import ConversationService
from app.conversation.response_language import RESPONSE_LANGUAGES
from app.conversation.store import ConversationStore
from app.settings.gui_language import GuiLanguageSettings, LoginLanguage
from app.settings.images import ImageGenerationSettings, ImageSettingsStore
from app.settings.response_language import ResponseLanguageSettings
from app.state.storage import JsonStore
from app.ui import localization
from app.ui.image_settings import ImageSettingsPage
from app.ui.localization import QLabel, QComboBox, language_runtime, ui_text
from app.ui.main_window import MainWindow
from app.ui.questions import QuestionComposer
from tools.ui_translations import CATALOGS, validate


@pytest.fixture
def app():
    instance = QApplication.instance() or QApplication([])
    runtime = language_runtime()
    runtime.apply(runtime.prepare("en"))
    instance.processEvents()
    yield instance
    runtime.apply(runtime.prepare("en"))
    instance.processEvents()


@pytest.mark.parametrize("language", [item for item in RESPONSE_LANGUAGES if item.code != "auto"], ids=lambda item: item.code)
def test_every_catalog_is_complete_and_compiled(language, app):
    tree = validate(language.code)
    if language.code != "en":
        assert (CATALOGS / f"{language.code}.qm").is_file()
        from PySide6.QtCore import QTranslator
        translator = QTranslator()
        assert translator.load(str(CATALOGS / f"{language.code}.qm"))
        for context in tree.getroot().findall("context"):
            for message in context.findall("message"):
                assert translator.translate(context.findtext("name"), message.findtext("source")) == message.findtext("translation")


def test_default_reads_do_not_write_and_settings_are_separate(tmp_path):
    preference = JsonStore(tmp_path / "state/ui_preferences_v1.json")
    preference.save({"greeting_message": "Settings", "unrelated": {"keep": True}})
    original = preference.path.read_bytes()
    settings = GuiLanguageSettings.for_preferences(preference)
    assert settings.code == "en" and not settings.store.path.exists()
    settings.select("hu")
    assert preference.path.read_bytes() == original
    assert GuiLanguageSettings.for_preferences(preference).code == "hu"
    assert set(settings.store.load()) == {"schema_version", "language_code"}


@pytest.mark.parametrize("record", [None, {}, {"schema_version": True, "language_code": "hu"},
    {"schema_version": 2, "language_code": "hu"}, {"schema_version": 1, "language_code": "missing"},
    {"schema_version": 1, "language_code": []}])
def test_unsupported_records_are_preserved(tmp_path, record):
    store = JsonStore(tmp_path / "language.json")
    store.save(record)
    before = store.path.read_bytes()
    settings = GuiLanguageSettings(store)
    assert settings.code == "en" and settings.load_error
    with pytest.raises(ValueError):
        settings.select("hu")
    assert store.path.read_bytes() == before


def test_all_language_switches_preserve_inputs_and_response_preference(app, tmp_path):
    from tests.test_personality import RequestRecorder
    reply_settings = ResponseLanguageSettings()
    reply_settings.select("hu")
    service = ConversationService(RequestRecorder(16384), ConversationStore(tmp_path / "chat.json"),
                                  response_language_settings=reply_settings)
    preferences = JsonStore(tmp_path / "state/ui_preferences_v1.json")
    preferences.save({"greeting_message": "Settings", "unrelated": "keep"})
    before = preferences.path.read_bytes()
    window = MainWindow(service, "SYNTHETIC", preferences_store=preferences)
    try:
        window.show()
        window.input.setPlainText("General\nC:\\Settings\\literal.json")
        cursor = window.input.textCursor()
        cursor.setPosition(3)
        window.input.setTextCursor(cursor)
        window.chat.add_message("User", "Settings")
        window.chat.add_message("Agent", "General")
        window.image_settings_page.choices["quality"].setCurrentIndex(1)
        quality = window.image_settings_page.choices["quality"].currentData()
        image_page = window.image_settings_page
        window.settings_panel.show_section("Appearance")
        window.settings_panel.show()
        for language in RESPONSE_LANGUAGES:
            if language.code == "auto":
                continue
            window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData(language.code))
            app.processEvents()
            expected = QCoreApplication.translate("OrsiUI", "General")
            assert window.settings_panel.navigation[0].text() == expected
            if language.code != "en":
                assert any(QCoreApplication.translate("OrsiUI", source) != source
                           for source in ("General", "Settings", "GUI Language")), language.code
            assert window.language_runtime.code == language.code
            assert window.gui_language_selector.toolTip() == window.gui_language_selector.accessibleDescription()
            assert window.tool_approval_toggle.toolTip() == window.tool_approval_toggle.accessibleDescription()
            assert window.input.toPlainText() == "General\nC:\\Settings\\literal.json"
            assert window.input.textCursor().position() == 3
            assert window.greeting_input.text() == "Settings"
            assert [message._content for message in window.chat._messages] == ["Settings", "General"]
            assert service.response_language_settings.current_code == "hu"
            assert window.response_language_selector.currentData() == "hu"
            assert window.image_settings_page is image_page
            assert image_page.choices["quality"].currentData() == quality
            assert window.settings_panel.pages.currentIndex() == 4
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("en"))
        app.processEvents()
        assert window.settings_panel.navigation[0].text() == "General"
        assert preferences.path.read_bytes() == before
    finally:
        window.close()


def test_failed_save_keeps_previous_effective_language_and_hides_private_error(app, tmp_path, monkeypatch):
    window = MainWindow(None, "SYNTHETIC", preferences_store=JsonStore(tmp_path / "ui.json"))
    try:
        monkeypatch.setattr(window.gui_language_settings.store, "save", Mock(side_effect=OSError("PRIVATE-ERROR")))
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("hu"))
        app.processEvents()
        assert window.language_runtime.code == "en"
        assert window.gui_language_selector.currentData() == "en"
        assert "previous choice" in window.gui_language_hint.text()
        assert "PRIVATE-ERROR" not in window.gui_language_hint.text()
    finally:
        window.close()


def test_auto_uses_system_locale_and_missing_catalog_does_not_save(app, tmp_path, monkeypatch):
    monkeypatch.setattr(localization, "system_language", lambda: "nl")
    window = MainWindow(None, "SYNTHETIC", preferences_store=JsonStore(tmp_path / "ui.json"))
    try:
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("auto"))
        app.processEvents()
        assert window.language_runtime.code == "nl"
        assert window.gui_language_settings.code == "auto"
        before = window.gui_language_settings.store.path.read_bytes()
        monkeypatch.setattr(localization, "CATALOGS", tmp_path / "missing")
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("hu"))
        app.processEvents()
        assert window.language_runtime.code == "nl" and window.gui_language_settings.code == "auto"
        assert window.gui_language_settings.store.path.read_bytes() == before
    finally:
        window.close()


def test_only_marked_text_changes_and_clear_revokes_bindings(app):
    label = QLabel(ui_text("{title}: custom answer", title="Settings"))
    user_label = QLabel("Settings")
    combo = QComboBox()
    combo.addItem(ui_text("Cancel"), "cancel")
    changed = []
    combo.currentIndexChanged.connect(changed.append)
    runtime = language_runtime()
    runtime.apply(runtime.prepare("hu"))
    app.processEvents()
    assert label.text() != "Settings: custom answer" and "Settings" in label.text()
    assert user_label.text() == "Settings" and combo.currentData() == "cancel"
    assert combo.currentText() != "Cancel" and changed == []
    label.clear()
    runtime.apply(runtime.prepare("nl"))
    app.processEvents()
    assert label.text() == "" and not label._ui_bindings
    label.deleteLater()
    user_label.deleteLater()
    combo.deleteLater()


def test_pending_question_form_keeps_original_answer_values(app):
    from tests.test_questions import batch
    form = QuestionComposer(batch())
    form.show()
    form.fields["work"].buttons[0].setChecked(True)
    form.fields["style"].combo.setCurrentIndex(1)
    form.fields["audience"].editor.setPlainText("Settings")
    form.additional.setPlainText("General")
    before = form.answer_text()
    runtime = language_runtime()
    runtime.apply(runtime.prepare("hu"))
    app.processEvents()
    assert form.answer_text() == before
    assert form.fields["work"].buttons[0].text() == "Photography"
    assert form.fields["style"].combo.currentData() == "minimal"
    assert form.additional.toPlainText() == "General"
    assert form.additional.placeholderText() != "Type your answer here…"
    form.close()


@pytest.mark.parametrize("code", ["hy", "ka"])
@pytest.mark.parametrize("theme", ["original", "conformist"])
def test_compact_translated_image_controls_fit_and_remain_reachable(app, code, theme):
    window = MainWindow(None, "SYNTHETIC")
    try:
        window.resize(760, 600)
        window.show()
        window.theme_controller.select(theme, persist=False)
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData(code))
        window.settings_panel.show_section("Image Generation")
        window.settings_panel.show()
        window.settings_panel.page_transition.cancel()
        app.processEvents()
        scroll = window.settings_panel.pages.currentWidget()
        assert scroll.widget().width() <= scroll.viewport().width()
        assert scroll.horizontalScrollBar().maximum() == 0
        for control in (*window.image_settings_page.choices.values(), window.image_settings_page.save_button,
                        window.image_settings_page.reset_button):
            scroll.ensureWidgetVisible(control)
            app.processEvents()
            bounds = control.rect().translated(control.mapTo(scroll.viewport(), QPoint()))
            assert scroll.viewport().rect().contains(bounds), (code, theme, control.objectName())
            if isinstance(control, QPushButton):
                option = QStyleOptionButton()
                control.initStyleOption(option)
                content = control.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, control)
                flags = (Qt.TextFlag.TextSingleLine if control.fontMetrics().horizontalAdvance(control.text()) <= content.width()
                         else Qt.TextFlag.TextWordWrap)
                text = control.fontMetrics().boundingRect(QRect(0, 0, content.width(), 1000), int(flags), control.text())
                assert text.height() <= content.height(), (code, theme, control.text())
        for control in window.image_settings_page.choices.values():
            caption = control.parentWidget().title
            assert caption.isVisible() and caption.height() > 0
            scroll.ensureWidgetVisible(caption)
            app.processEvents()
            assert scroll.viewport().rect().contains(caption.rect().translated(caption.mapTo(scroll.viewport(), QPoint())))
    finally:
        window.close()


def test_translated_image_quality_saves_original_enum(app, tmp_path):
    store = ImageSettingsStore(ImageGenerationSettings(), tmp_path / "images.json")
    language_runtime().apply(language_runtime().prepare("hu"))
    page = ImageSettingsPage(store, store.select)
    selector = page.choices["quality"]
    selector.setCurrentIndex(selector.findData("high"))
    assert selector.currentText() != "high"
    page._save()
    assert store.current.quality == "high"
    page.close()


def test_pending_approval_relabels_without_changing_the_operation(app):
    from types import SimpleNamespace
    from app.ui.approvals import create_inline_approval
    record = SimpleNamespace(capability="filesystem.write_text", resource="C:\\Settings\\literal.json",
                             approval_preview="Settings", approval_id="synthetic-approval")
    service = SimpleNamespace(approval_status=lambda value: "pending", resolve_approval=Mock())
    panel = create_inline_approval(None, service, record, lambda: None)
    panel.show()
    language_runtime().apply(language_runtime().prepare("hu"))
    app.processEvents()
    assert panel.findChild(NativeLabel, "approvalTitle").text() != "Write file?"
    assert panel._record is record and record.approval_preview == "Settings"
    service.resolve_approval.assert_not_called()
    panel.reject()
    service.resolve_approval.assert_called_once_with("synthetic-approval", False)


def test_desktop_notification_uses_gui_language_without_conversation_content(app, monkeypatch):
    window = MainWindow(None, "SYNTHETIC")
    try:
        manager = window.notifications
        manager.backend = Mock()
        manager.backend.show_message.return_value = True
        monkeypatch.setattr(manager, "_needs_attention", lambda: True)
        monkeypatch.setattr(manager, "_ensure_backend", lambda: None)
        monkeypatch.setattr(manager, "play_sound", lambda **kwargs: None)
        language_runtime().apply(language_runtime().prepare("hu"))
        manager.notify("approval")
        if os.name == "nt":
            arguments = manager.backend.show_message.call_args.args
        else:
            arguments = manager.backend.showMessage.call_args.args
        assert arguments[0] == QCoreApplication.translate("OrsiUI", "O.R.S.I needs approval")
        assert arguments[0] != "O.R.S.I needs approval"
    finally:
        window.close()


def test_login_cache_is_content_free_isolated_and_preserves_corruption(tmp_path):
    cache = LoginLanguage(tmp_path / "login.json")
    first, second = str(uuid4()), str(uuid4())
    cache.remember("hu", first)
    cache.remember("nl", second)
    assert cache.code_for(first) == "hu" and cache.code_for(second) == "nl"
    assert cache.code_for(str(uuid4())) == "en"
    assert cache.store.load() == {"schema_version": 1, "profiles": {first: "hu", second: "nl"}}
    cache.store.path.write_bytes(b"invalid preserved record")
    cache.remember("en", first)
    assert cache.code_for(first) == "en"
    assert cache.store.path.read_bytes() == b"invalid preserved record"


def test_encrypted_profile_restores_gui_language_before_and_after_unlock(app, tmp_path):
    from app.ui.profile_application import ProfileApplication
    from app.vault.profiles import ProfileManager
    from tests.test_profile_onboarding import close_controller
    from tests.test_vault_controls import PASSWORD, build_synthetic
    application_root = tmp_path / "application"
    application_root.mkdir()
    manager = ProfileManager(application_root)
    first_root = tmp_path / "first-profile"
    manager.create(first_root, password=PASSWORD)
    owner = ProfileApplication(app, application_root, build_synthetic, manager=manager)
    try:
        owner.start()
        previous = owner.window.gui_language_settings
        selector = owner.window.gui_language_selector
        selector.setCurrentIndex(selector.findData("hu"))
        app.processEvents()
        first_id = manager.locator.profile_id
        owner.transition(manager.lock)
        app.processEvents()
        assert previous.closed and previous.store is None and previous.code is None
        assert owner.window.service is None and owner.window.language_runtime.code == "hu"
        assert owner.window.login_panel.findChild(NativeLabel, "loginHeading").text() != "Unlock your profile"
        owner.window.personal_profile_page.password.setText(PASSWORD.decode())
        owner.window.personal_profile_page._unlock()
        assert owner.window.gui_language_settings.code == "hu"
        owner.transition(lambda: manager.create(tmp_path / "second-profile", password=PASSWORD))
        assert owner.window.gui_language_settings.code == "en"
        assert owner.login_language.code_for(first_id) == "hu"
        owner.transition(lambda: manager.select(first_root, password=PASSWORD))
        assert owner.window.language_runtime.code == "hu"
        owner.transition(manager.lock)
    finally:
        close_controller(app, owner)
    restarted = ProfileApplication(app, application_root, build_synthetic)
    try:
        restarted.start()
        assert restarted.window.language_runtime.code == "hu" and restarted.window.service is None
        restarted.window.personal_profile_page.password.setText(PASSWORD.decode())
        restarted.window.personal_profile_page._unlock()
        assert restarted.window.gui_language_settings.code == "hu"
    finally:
        close_controller(app, restarted)
