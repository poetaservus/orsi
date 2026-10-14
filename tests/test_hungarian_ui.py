"""Essential Hungarian pilot checks: composition, binding, literal data and review integrity."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.state.storage import JsonStore
from app.ui.chat import _elapsed_label
from app.ui.localization import QLabel, QComboBox, language_runtime, ui_extra, ui_text
from app.ui.main_window import MainWindow
from app.ui.operation_review import OperationReviewDialog
from tests.test_gui_language import app
from tests.test_skill_settings_ui import ui as skill_ui
from tools import ui_translations as catalogs


def test_review_record_detects_copy_edits_and_does_not_claim_native_approval():
    tree = catalogs.validate("hu")
    record = json.loads((catalogs.REVIEW_RECORDS / "hu-review.json").read_text(encoding="utf-8"))
    assert record["status"] == "editorially_revised"
    assert record["native_review"] == {"status": "pending", "reviewer": None, "date": None}
    edited = copy.deepcopy(tree)
    edited.getroot().find("context/message/translation").text += " changed"
    with pytest.raises(ValueError, match="Editorial review is stale"):
        catalogs.validate_review("hu", edited)


def test_update_keeps_context_notes_and_does_not_clear_unfinished_state(tmp_path, monkeypatch):
    original = catalogs.validate("hu")
    (tmp_path / "hu.ts").write_bytes((catalogs.CATALOGS / "hu.ts").read_bytes())
    monkeypatch.setattr(catalogs, "CATALOGS", tmp_path)
    catalogs.update("hu")
    updated = catalogs.validate("hu")
    assert catalogs.review_fingerprints(updated) == catalogs.review_fingerprints(original)
    for before, after in zip(original.getroot().iter("message"), updated.getroot().iter("message")):
        assert before.findtext("extracomment") == after.findtext("extracomment")
        assert [item.attrib for item in before.findall("location")] == [item.attrib for item in after.findall("location")]
    updated.getroot().find("context/message/translation").set("type", "unfinished")
    updated.write(tmp_path / "hu.ts", encoding="utf-8", xml_declaration=True)
    catalogs.update("hu")
    with pytest.raises(ValueError, match="Unfinished translation"):
        catalogs.validate("hu")


def test_nested_counts_contexts_and_literal_values_survive_switching(app):
    runtime = language_runtime()
    literal = QLabel("Encrypted")
    source = QLabel(ui_extra("Source: {location}", location="Encrypted/skills/SKILL.md"))
    items = [QLabel(ui_text("{value_0} {value_1} · {value_2} {value_3} · {value_4} KB",
                           value_0=count, value_1=ui_extra("skill" if count == 1 else "skills"),
                           value_2=count, value_3=ui_extra("reference" if count == 1 else "references"), value_4="1.0"))
             for count in (0, 1, 2, 21)]
    timing = QLabel(_elapsed_label("Worked", 3730))
    selector = QComboBox()
    selector.addItem(ui_extra("Encrypted"), "encrypted")
    selector.insertItem(0, ui_extra("Unencrypted"), "unencrypted")
    selector.setItemText(0, ui_extra("Unlocked"))
    selector.setCurrentIndex(1)
    changed = []
    selector.currentIndexChanged.connect(changed.append)
    try:
        for language in ("hu", "en", "hu", "nl"):
            runtime.apply(runtime.prepare(language))
            app.processEvents()
            assert literal.text() == "Encrypted"
            assert source.text() == ("Forrás: " if language == "hu" else "Source: ") + "Encrypted/skills/SKILL.md"
            for count, label in zip((0, 1, 2, 21), items):
                expected = (f"{count} képesség · {count} hivatkozás · 1.0 KB" if language == "hu" else
                            f"{count} {'skill' if count == 1 else 'skills'} · {count} {'reference' if count == 1 else 'references'} · 1.0 KB")
                assert label.text() == expected
            assert timing.text() == ("Elkészült · 1 ó 2 p 10 mp" if language == "hu" else "Worked for 1 h 2 m 10s")
            assert selector.currentText() == ("Titkosított" if language == "hu" else "Encrypted")
            assert selector.itemText(0) == ("Feloldva" if language == "hu" else "Unlocked")
            assert selector.currentData() == "encrypted" and not changed
    finally:
        for widget in (literal, source, timing, selector, *items):
            widget.deleteLater()


def test_real_hungarian_review_banner_uses_accusative_after_counts(app, tmp_path):
    window = MainWindow(None, "SYNTHETIC", preferences_store=JsonStore(tmp_path / "ui.json"))
    snapshot = SimpleNamespace(required=True, restart_required=False, operations=(None,))
    window.service = SimpleNamespace(operation_review=lambda: snapshot)
    try:
        window.input.setPlainText("Literal draft: Encrypted")
        for count in (1, 2, 21):
            snapshot.operations = (None,) * count
            window._refresh_operation_review()
            window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("hu"))
            app.processEvents()
            assert window.operation_review_label.text().startswith(
                f"További módosítások előtt {count} félbeszakadt műveletet ellenőrizni kell.")
            window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("en"))
            app.processEvents()
            assert f"{count} interrupted operation" in window.operation_review_label.text()
            assert window.input.toPlainText() == "Literal draft: Encrypted"
        assert JsonStore(tmp_path / "gui_language_v1.json").load()["language_code"] == "en"
    finally:
        window.service = None
        window.close()


def test_review_details_translate_labels_keep_identifiers_and_clear_on_close(app):
    runtime = language_runtime()
    item = SimpleNamespace(capability="filesystem.write_text", updated_at_ms=0,
                           session_id="Encrypted", turn_id="Write file", call_id="Unencrypted")
    service = SimpleNamespace(acknowledge_operation_review=Mock())
    dialog = OperationReviewDialog(None, service, SimpleNamespace(operations=(item,), restart_required=False))
    try:
        for language in ("hu", "en", "hu", "nl"):
            runtime.apply(runtime.prepare(language))
            app.processEvents()
            text = dialog.details.toPlainText()
            assert text.startswith("Fájl mentése · " if language == "hu" else "Write file · ")
            assert ("Beszélgetés: Encrypted · Üzenetváltás: Write file\nMűvelet: Unencrypted" if language == "hu" else
                    "Chat: Encrypted · Turn: Write file\nOperation: Unencrypted") in text
            assert dialog.details.isReadOnly() and not dialog.acknowledge.isEnabled()
            service.acknowledge_operation_review.assert_not_called()
        dialog.reject()
        runtime.apply(runtime.prepare("hu"))
        app.processEvents()
        assert dialog.details.toPlainText() == "" and dialog._operations is None
        service.acknowledge_operation_review.assert_not_called()
    finally:
        dialog.reject()


def test_actual_skill_preview_relabels_only_owned_copy(skill_ui):
    window, dialog, service, model = skill_ui
    page = dialog.page
    page.source.setText("Encrypted/SKILL.md")
    result = SimpleNamespace(definition=SimpleNamespace(name="Settings", description="Encrypted"),
                             packages=(), skill_count=2, reference_count=3, total_bytes=2048,
                             source="Encrypted/SKILL.md")
    page._action = "preview"
    page._succeeded(result)
    runtime = language_runtime()
    for language in ("hu", "en", "hu", "nl"):
        runtime.apply(runtime.prepare(language))
        window.show()
        window.update()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        assert page.preview_name.text() == "Settings" and page.preview_description.text() == "Encrypted"
        assert page.preview_source.text() == ("Forrás: " if language == "hu" else "Source: ") + result.source
        assert page.preview_summary.text() == ("2 képesség · 3 hivatkozás · 2.0 KB" if language == "hu" else
                                               "2 skills · 3 references · 2.0 KB")
        assert page.prepared is result and page.source.text() == "Encrypted/SKILL.md"
        assert not model.requests
    runtime.apply(runtime.prepare("en"))


def test_hungarian_profile_captions_fit_fixed_controls_and_compact_cards(app, tmp_path):
    from PySide6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton
    from app.ui.profile_application import ProfileApplication
    from app.vault.profiles import ProfileManager
    from tests.test_profile_onboarding import close_controller
    from tests.test_vault_controls import PASSWORD, build_synthetic
    application_root = tmp_path / "application"
    application_root.mkdir()
    manager = ProfileManager(application_root)
    manager.create(tmp_path / "profile", password=PASSWORD)
    owner = ProfileApplication(app, application_root, build_synthetic, manager=manager)
    try:
        owner.start()
        window = owner.window
        window.gui_language_selector.setCurrentIndex(window.gui_language_selector.findData("hu"))
        page = window.personal_profile_page
        for width, height in ((1280, 900), (760, 600)):
            window.resize(width, height)
            window.settings_panel.show_section("Personal profile")
            window.settings_panel.show()
            window.settings_panel.page_transition.cancel()
            for section, controls in (("Storage", (page.quota_save, page.idle_save)),
                                      ("Backups", (page.backup_save,)), ("Cloud access", (page.consent,))):
                page.show_section(section)
                page.tab_transition.cancel()
                app.processEvents()
                scroll = page.sections[section]
                for control in controls:
                    scroll.ensureWidgetVisible(control)
                    app.processEvents()
                    option = QStyleOptionButton()
                    control.initStyleOption(option)
                    element = QStyle.SubElement.SE_CheckBoxContents if isinstance(control, QCheckBox) else QStyle.SubElement.SE_PushButtonContents
                    bounds = control.style().subElementRect(element, option, control)
                    assert control.fontMetrics().horizontalAdvance(control.text()) <= bounds.width(), control.text()
                    assert scroll.widget().width() <= scroll.viewport().width()
    finally:
        close_controller(app, owner)
