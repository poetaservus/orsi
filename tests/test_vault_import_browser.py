"""Explicit host-file/folder copies and clear, separate legacy import navigation."""
import json
import os

import pytest
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QLineEdit, QPushButton

from app.ui.profile_application import ProfileApplication
from app.vault.migration import apply_migration, prepare_file_import, prepare_folder_import, retained_originals
from app.vault.types import Domain, VaultError
from tests.test_vault_controls import build_synthetic, ciphertext, manager, qt


def test_host_folder_import_preserves_nested_paths_and_originals(manager, tmp_path):
    source = tmp_path / "Host project"
    (source / "reference").mkdir(parents=True)
    (source / "guide.txt").write_bytes(b"first document")
    (source / "reference/guide.txt").write_bytes(b"nested document")
    plan = prepare_folder_import(source)
    receipt = apply_migration(manager.session, plan)
    report = json.loads(manager.vault().read(receipt))
    assert report["verified"] and len(report["records"]) == 2
    for relative, expected in (("guide.txt", b"first document"), ("reference/guide.txt", b"nested document")):
        assert manager.vault().read("imports/" + plan.identity + "/Host project/" + relative) == expected
        assert (source / relative).read_bytes() == expected
    assert set(retained_originals(manager.session, receipt)) == {str(source / "guide.txt"), str(source / "reference/guide.txt")}
    assert manager.vault().list_paths(domain=Domain.CREDENTIAL) == ()
    ciphertext(manager.locator.root)


def test_selected_files_keep_same_names_and_abort_changed_source(manager, tmp_path):
    first, second = tmp_path / "first/guide.txt", tmp_path / "second/guide.txt"
    for path, data in ((first, b"first copy"), (second, b"second copy")):
        path.parent.mkdir()
        path.write_bytes(data)
    plan = prepare_file_import((first, second, first))
    assert len(plan.writes) == 2 and len({write.path for write in plan.writes}) == 2
    apply_migration(manager.session, plan)
    assert {manager.vault().read(write.path) for write in plan.writes} == {b"first copy", b"second copy"}
    before = manager.vault().list_paths()
    changed = prepare_file_import((first, second))
    first.write_bytes(b"edited after selection")
    with pytest.raises(VaultError):
        apply_migration(manager.session, changed)
    assert manager.vault().list_paths() == before
    assert first.read_bytes() == b"edited after selection" and second.read_bytes() == b"second copy"


def test_empty_missing_and_shared_import_sources_are_rejected(tmp_path):
    with pytest.raises(VaultError):
        prepare_file_import(())
    with pytest.raises(VaultError):
        prepare_folder_import(tmp_path / "missing")
    with pytest.raises(VaultError, match="no files"):
        prepare_folder_import(tmp_path)
    source = tmp_path / "guide.txt"
    source.write_bytes(b"shared document")
    os.link(source, tmp_path / "alias.txt")
    with pytest.raises(VaultError, match="hardlink"):
        prepare_folder_import(tmp_path)
    assert source.read_bytes() == b"shared document"


def test_file_and_folder_buttons_browse_cancel_and_refresh_vault(qt, manager, monkeypatch, tmp_path):
    source = tmp_path / "Host documents"
    source.mkdir()
    (source / "one.txt").write_bytes(b"selected file")
    (source / "two.txt").write_bytes(b"folder file")
    selected = []
    folder = ""
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: (selected, ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: folder)
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        controller.window.personal_profile_page.show_section("Data")
        def click(title):
            page = controller.window.personal_profile_page
            next(button for button in page.findChildren(QPushButton) if button.text() == title).click()
        before = manager.vault().list_paths()
        click("Import files…")
        click("Import folder…")
        assert manager.vault().list_paths() == before
        selected = [str(source / "one.txt"), str(source / "two.txt")]
        click("Import files…")
        folder = str(source)
        click("Import folder…")
        page = controller.window.personal_profile_page
        imported = [path for path in manager.vault().list_paths() if path.startswith("imports/")]
        assert len(imported) == 4
        assert {manager.vault().read(path) for path in imported} == {b"selected file", b"folder file"}
        assert "completed and verified" in page.status.text()
        assert page.tabs.tabText(page.tabs.currentIndex()) == "Data"
        assert page.records.count() >= 4
        assert (source / "one.txt").read_bytes() == b"selected file"
        assert (source / "two.txt").read_bytes() == b"folder file"
        assert manager.vault().list_paths(domain=Domain.CREDENTIAL) == ()
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)


def test_legacy_dialog_has_visible_labels_and_folder_browsers(qt, manager, monkeypatch, tmp_path):
    source = tmp_path / "Previous O.R.S.I"
    (source / "documents").mkdir(parents=True)
    (source / "documents/guide.txt").write_bytes(b"legacy document")
    chosen = ""
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: chosen)
    def inspect(dialog):
        nonlocal chosen
        dialog.show()
        qt.processEvents()
        fields = {field.accessibleName(): field for field in dialog.findChildren(QLineEdit)}
        application, skills = fields["Previous O.R.S.I application folder"], fields["Personal skills folder"]
        assert any(caption.buddy() is application and caption.isVisible() for caption in dialog.findChildren(QLabel))
        assert not application.text() and not skills.isVisible()
        checks = {check.text(): check for check in dialog.findChildren(QCheckBox)}
        buttons = dialog.findChild(QDialogButtonBox)
        submit = buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert submit.text() == "Import selected data" and not submit.isEnabled()
        checks["Personal documents"].setChecked(True)
        assert not submit.isEnabled()
        browse = next(button for button in dialog.findChildren(QPushButton)
                      if button.accessibleName() == "Browse for previous o.r.s.i application folder")
        browse.click()
        assert not application.text()
        chosen = str(source)
        browse.click()
        assert application.text() == str(source) and submit.isEnabled()
        checks["Personal skills and their documentation"].setChecked(True)
        qt.processEvents()
        assert skills.isVisible()
        assert any(caption.buddy() is skills and caption.isVisible() for caption in dialog.findChildren(QLabel))
        chosen = str(tmp_path)
        next(button for button in dialog.findChildren(QPushButton)
             if button.accessibleName() == "Browse for personal skills folder").click()
        assert skills.text() == str(tmp_path)
        checks["Personal skills and their documentation"].setChecked(False)
        assert not skills.isVisible()
        dialog.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", inspect)
    controller = ProfileApplication(qt, manager.application_root, build_synthetic, manager=manager)
    try:
        controller.start()
        controller.window.personal_profile_page._migrate()
        assert manager.vault().read("documents/guide.txt") == b"legacy document"
        assert (source / "documents/guide.txt").read_bytes() == b"legacy document"
    finally:
        controller.shutdown()
        controller.window.close()
        qt.removeEventFilter(controller)
