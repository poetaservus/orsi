"""Settings-only skill import/review, installation and removal."""
from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from html import escape

from app.runtime.skills.contracts import SkillLoadError, SkillParseError
from app.runtime.skills.import_source import SkillImportError, prepare_import
from app.runtime.skills.installer import SkillInstallError
from app.ui.motion import install_smooth_scroll


class SkillSourceInput(QLineEdit):
    """Drop one folder/file/link into Settings, never into the composer."""

    def dragEnterEvent(self, event):  # noqa: N802
        mime = event.mimeData()
        if (len(mime.urls()) == 1 if mime.hasUrls() else mime.hasText()):
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if len(urls) != 1:
                return
            value = urls[0].toLocalFile() if urls[0].isLocalFile() else urls[0].toString()
        else:
            value = mime.text().strip()
        self.setText(value)
        event.acceptProposedAction()


class SkillSettingsWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service, action, value, parent=None):
        super().__init__(parent)
        self.service, self.action, self.value = service, action, value

    @Slot()
    def run(self):
        try:
            if self.action == "preview":
                result = prepare_import(self.value, max_bytes=self.service.skill_registry.max_bytes)
            elif self.action == "install":
                result = self.service.install_skill(self.value)
            elif self.action == "remove":
                result = self.service.remove_skill(self.value)
            else:
                raise SkillImportError("Choose a skill operation.")
            self.succeeded.emit(result)
        except (SkillImportError, SkillInstallError, SkillLoadError, SkillParseError, RuntimeError) as error:
            self.failed.emit(str(error)[:500])
        except Exception:
            self.failed.emit("The skill operation could not be completed. Try again.")


class SkillSettingsPage(QWidget):
    catalog_changed = Signal()
    close_requested = Signal()
    busy_changed = Signal(bool)
    idle = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.prepared = None
        self.thread = self.worker = None
        self._action = None
        self._available = getattr(service, "skill_registry", None) is not None
        self.setObjectName("skillSettingsPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        source_hint = QLabel("Paste a GitHub repository or skill-file link, or drop a folder/file.")
        source_hint.setWordWrap(True)
        layout.addWidget(source_hint)
        source_row = QHBoxLayout()
        self.source = SkillSourceInput()
        self.source.setObjectName("skillSource")
        self.source.setAccessibleName("Skill repository, folder or Markdown file")
        self.source.setPlaceholderText("GitHub repository, skill folder or SKILL.md link")
        self.source.setMaxLength(4096)
        self.source.setAcceptDrops(True)
        self.browse = QPushButton("Choose file…")
        self.browse_folder = QPushButton("Choose folder…")
        source_row.addWidget(self.source, 1)
        source_row.addWidget(self.browse)
        source_row.addWidget(self.browse_folder)
        layout.addLayout(source_row)
        self.preview_button = QPushButton("Preview")
        self.preview_button.setObjectName("skillPreview")
        self.preview_button.setEnabled(False)
        layout.addWidget(self.preview_button)
        self.preview_name = QLabel()
        self.preview_description = QLabel()
        self.preview_source = QLabel()
        self.preview_summary = QLabel()
        for label in (self.preview_name, self.preview_description, self.preview_source, self.preview_summary):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.hide()
            layout.addWidget(label)
        self.preview_source.setWordWrap(False)
        self.preview_source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.preview_packages = QListWidget()
        install_smooth_scroll(self.preview_packages)
        self.preview_packages.setAccessibleName("Packages to install")
        self.preview_packages.setMaximumHeight(100)
        self.preview_packages.hide()
        layout.addWidget(self.preview_packages)
        self.scope = QLabel("Folders and repositories include supporting Markdown documents. File links import "
                            "only the main instructions. Selected skills can read their references when tools are enabled.")
        self.scope.setWordWrap(True)
        self.scope.setObjectName("skillsHint")
        layout.addWidget(self.scope)
        self.install_button = QPushButton("Install")
        self.install_button.setObjectName("skillInstall")
        self.install_button.setEnabled(False)
        layout.addWidget(self.install_button)
        installed_row = QHBoxLayout()
        installed_row.addWidget(QLabel("Installed skills"), 1)
        self.remove_button = QPushButton("Remove…")
        installed_row.addWidget(self.remove_button)
        layout.addLayout(installed_row)
        self.installed = QListWidget()
        self.installed.setObjectName("installedSkills")
        install_smooth_scroll(self.installed)
        self.installed.setMinimumHeight(150)
        self.installed.setAccessibleName("Installed skills")
        layout.addWidget(self.installed, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.close_button = QPushButton("Done")
        layout.addWidget(self.close_button)
        self.close_button.hide()
        # Enter in the source prepares a preview; it never installs implicitly.
        for button in (self.browse, self.browse_folder, self.preview_button, self.install_button, self.remove_button, self.close_button):
            button.setAutoDefault(False)
        self.source.returnPressed.connect(self._preview)
        self.source.textChanged.connect(self._source_changed)
        self.browse.clicked.connect(self._browse)
        self.browse_folder.clicked.connect(self._browse_folder)
        self.preview_button.clicked.connect(self._preview)
        self.install_button.clicked.connect(self._install)
        self.remove_button.clicked.connect(self._remove)
        self.installed.currentItemChanged.connect(self._update_buttons)
        self.close_button.clicked.connect(self.close_requested)
        self._refresh_installed()

    def _source_changed(self):
        self.prepared = None
        self.preview_packages.clear()
        self.preview_packages.hide()
        for label in (self.preview_name, self.preview_description, self.preview_source, self.preview_summary):
            label.hide()
        self.status.clear()
        self._update_buttons()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a skill", "", "Markdown skills (*.md)")
        if path:
            self.source.setText(path)

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a skill folder")
        if path:
            self.source.setText(path)

    def _refresh_installed(self):
        self.installed.clear()
        registry = getattr(self.service, "skill_registry", None)
        for skill in registry.list() if registry is not None else ():
            item = QListWidgetItem(" ".join(skill.name.split())[:128])
            item.setData(Qt.ItemDataRole.UserRole, skill.name)
            item.setData(Qt.ItemDataRole.UserRole + 1,
                         skill.source_path.is_relative_to(self.service.skill_registry.global_root))
            item.setToolTip("<qt>" + escape(" ".join(skill.description.split())[:512]) + "</qt>")
            self.installed.addItem(item)
        if self.installed.count():
            self.installed.setCurrentRow(0)
        self._update_buttons()

    def _update_buttons(self, *args):
        busy = self.thread is not None or not self._available
        self.source.setEnabled(not busy)
        self.browse.setEnabled(not busy)
        self.browse_folder.setEnabled(not busy)
        self.preview_button.setEnabled(not busy and bool(self.source.text().strip()))
        self.install_button.setEnabled(not busy and self.prepared is not None)
        item = self.installed.currentItem()
        self.remove_button.setEnabled(not busy and item is not None
                                      and bool(item.data(Qt.ItemDataRole.UserRole + 1)))
        self.installed.setEnabled(not busy)
        self.close_button.setEnabled(not busy)

    def set_available(self, available):
        self._available = bool(available and getattr(self.service, "skill_registry", None) is not None)
        self._update_buttons()

    def _preview(self):
        if self._available and self.thread is None and self.source.text().strip():
            self.prepared = None
            self.preview_packages.clear()
            self.preview_packages.hide()
            for label in (self.preview_name, self.preview_description, self.preview_source, self.preview_summary):
                label.hide()
            self._start("preview", self.source.text())

    def _install(self):
        if self.prepared is not None:
            self._start("install", self.prepared)

    def _remove(self):
        if not self._available or self.thread is not None:
            return
        item = self.installed.currentItem()
        if item is None or not item.data(Qt.ItemDataRole.UserRole + 1):
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Remove skill")
        confirm.setTextFormat(Qt.TextFormat.PlainText)
        confirm.setText('Remove "' + " ".join(name.split())[:128] + '" from installed skills?')
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if confirm.exec() == QMessageBox.StandardButton.Yes:
            self._start("remove", name)

    def _start(self, action, value):
        if self.thread is not None or not self._available:
            return
        self._action = action
        self.status.setText({"preview": "Checking skill…", "install": "Installing…", "remove": "Removing…"}[action])
        self.worker = SkillSettingsWorker(self.service, action, value, self)
        self.thread = self.worker
        self.worker.succeeded.connect(self._succeeded)
        self.worker.failed.connect(self.status.setText)
        self.thread.finished.connect(self._finished)
        self._update_buttons()
        self.busy_changed.emit(True)
        self.thread.start()

    @Slot(object)
    def _succeeded(self, result):
        if getattr(self, "_profile_closed", False):
            return
        if self._action == "preview":
            self.prepared = result
            skill = result.definition
            names = ", ".join(" ".join(package.skill.name.split())[:128] for package in result.packages) if result.packages else skill.name
            self.preview_name.setText(names if len(names) <= 240 else names[:237] + "…")
            self.preview_packages.clear()
            for package in result.packages:
                item = QListWidgetItem(" ".join(package.skill.name.split())[:128])
                item.setToolTip("<qt>" + escape(" ".join(package.skill.description.split())[:512]) + "</qt>")
                self.preview_packages.addItem(item)
            self.preview_packages.setVisible(result.skill_count > 1)
            description = " ".join(skill.description.split())
            self.preview_description.setText(description if len(description) <= 240 else description[:237] + "…")
            self.preview_description.setToolTip("<qt>" + escape(description[:512]) + "</qt>")
            self._refresh_preview_source()
            self.preview_source.setToolTip("<qt>" + escape(result.source[:2048]) + "</qt>")
            skill_label = "skill" if result.skill_count == 1 else "skills"
            reference_label = "reference" if result.reference_count == 1 else "references"
            self.preview_summary.setText(f"{result.skill_count} {skill_label} · {result.reference_count} {reference_label} · "
                                         f"{result.total_bytes / 1024:.1f} KB")
            for label in (self.preview_name, self.preview_description, self.preview_source, self.preview_summary):
                label.show()
            self.status.setText("Ready to install.")
            self.layout().activate()
            self.updateGeometry()
        else:
            if self._action == "install":
                self.status.setText(f"Installed {len(result.installed)}; already present {len(result.already_installed)}. "
                                    "Available in /skill.")
            else:
                self.status.setText("Skill removed.")
            self._refresh_installed()
            self.catalog_changed.emit()

    def revoke_profile(self):
        self._profile_closed = True
        self._available = False
        self.prepared = None
        self.source.clear()
        self.installed.clear()
        self.preview_packages.clear()
        for label in (self.preview_name, self.preview_description, self.preview_source, self.preview_summary, self.status):
            label.clear()
            label.setToolTip("")
        self.setEnabled(False)

    def _refresh_preview_source(self):
        if self.prepared is not None:
            self.preview_source.setText(self.preview_source.fontMetrics().elidedText(
                "Source: " + self.prepared.source[:2048], Qt.TextElideMode.ElideRight, max(0, self.width() - 16)))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._refresh_preview_source()

    @Slot()
    def _finished(self):
        # finished may precede native thread-local cleanup. Join before releasing
        # the owned thread or allowing another operation/closing the dialog.
        self.thread.wait()
        self.thread.deleteLater()
        self.thread = self.worker = None
        self._update_buttons()
        self.busy_changed.emit(False)
        self.idle.emit()

    def closeEvent(self, event):  # noqa: N802
        if self.thread is not None:
            event.ignore()
        else:
            super().closeEvent(event)


class SkillSettingsDialog(QDialog):
    """Compatibility shell around the same reusable skill controls."""
    catalog_changed = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.setObjectName("skillSettings")
        self.setWindowTitle("Skills")
        self.setMinimumWidth(600)
        self.resize(640, 610)
        self.setStyleSheet(_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        self.page = SkillSettingsPage(service, self)
        layout.addWidget(self.page)
        self.page.close_button.show()
        self.page.close_requested.connect(self.accept)
        self.page.catalog_changed.connect(self.catalog_changed)

    @property
    def thread(self):
        return self.page.thread

    def __getattr__(self, name):
        page = self.__dict__.get("page")
        if page is not None:
            return getattr(page, name)
        raise AttributeError(name)

    def done(self, result):
        if self.page.thread is None:
            super().done(result)

    def closeEvent(self, event):  # noqa: N802
        if self.page.thread is not None:
            event.ignore()
        else:
            super().closeEvent(event)


_STYLE = """
QDialog#skillSettings { background: #20242d; color: #d9dce3; }
QDialog#skillSettings QLabel { color: #d9dce3; background: transparent; font-family: Saira; font-size: 14px; }
QDialog#skillSettings QLabel#skillsTitle { font-size: 19px; }
QDialog#skillSettings QLabel#skillsHint { color: #b9bfcc; font-size: 12px; }
QDialog#skillSettings QLineEdit, QDialog#skillSettings QListWidget {
    background: #171a21; color: #d9dce3; border: 1px solid rgba(153, 165, 184, 55);
    border-radius: 6px; padding: 7px; font-family: Saira; font-size: 14px;
    selection-background-color: #3e4551;
}
QDialog#skillSettings QPushButton {
    background: #303640; color: #d9dce3; border: 1px solid rgba(153, 165, 184, 36);
    border-radius: 6px; padding: 7px 12px; font-family: Saira; font-size: 14px;
}
QDialog#skillSettings QPushButton:hover { background: #3e4551; }
QDialog#skillSettings QPushButton:disabled { color: #767d89; background: #252a32; }
QDialog#skillSettings QListWidget::item { padding: 4px 6px; border: none; }
QDialog#skillSettings QListWidget::item:selected { background: #3e4551; }
"""
