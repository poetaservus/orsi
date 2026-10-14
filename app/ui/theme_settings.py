"""Small Appearance controls for selecting, importing and exporting themes."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton

from app.ui.inputs import ScrollSafeComboBox
from app.ui.theme_runtime import PreparedTheme
from app.ui.themes import BUILTIN_IDS, ThemeError, export_folder, import_folder


class ThemeControls:
    def __init__(self, panel, window, layout):
        self.panel, self.window = panel, window
        self.controller = window.theme_controller
        self.selector = ScrollSafeComboBox(panel)
        self.selector.setAccessibleName("Theme")
        self.selector.setToolTip("Change the appearance immediately")
        window.theme_selector = self.selector
        panel._row(layout, "Theme", "Colors, background, font and icons", self.selector)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.add = QPushButton("Add theme…", panel)
        self.export = QPushButton("Export current theme…", panel)
        self.add.setAccessibleName("Add theme")
        self.export.setAccessibleName("Export current theme")
        actions.addWidget(self.add)
        actions.addWidget(self.export)
        actions.addStretch()
        layout.addLayout(actions)
        self.status = QLabel(self.controller.notice, panel)
        self.status.setObjectName("settingsDescription")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Theme status")
        layout.addWidget(self.status)
        layout.addSpacing(12)
        self.refresh()
        self.selector.currentIndexChanged.connect(self.select)
        self.add.clicked.connect(self.choose_import)
        self.export.clicked.connect(self.choose_export)

    def refresh(self):
        self.selector.blockSignals(True)
        entries = [(package["manifest"]["name"], identity)
                   for identity, package in self.controller.repository.packages.items()]
        existing = [(self.selector.itemText(index), self.selector.itemData(index))
                    for index in range(self.selector.count())]
        if entries != existing:
            self.selector.clear()
            for name, identity in entries:
                self.selector.addItem(name, identity)
        self.selector.setCurrentIndex(self.selector.findData(self.controller.current.identity))
        self.selector.blockSignals(False)

    def select(self, index):
        identity = self.selector.itemData(index)
        if identity is None:
            return
        try:
            self.controller.select(identity)
            self.status.setText(self.controller.notice)
        except Exception as error:
            self.status.setText(str(error) if isinstance(error, ThemeError) else "Could not save the theme selection. Your settings were preserved.")
        self.refresh()

    def import_path(self, path):
        package = import_folder(path)
        prepared = PreparedTheme(package)
        prepared.close()
        self.controller.repository.add(package)
        self.controller.select(package["manifest"]["id"])
        self.refresh()
        self.status.setText(self.controller.notice or "Theme added.")

    def choose_import(self):
        path, _ = QFileDialog.getOpenFileName(self.panel, "Add theme", "", "Theme manifest (theme.json *.json)")
        if not path:
            return
        try:
            self.import_path(path)
        except Exception as error:
            self.status.setText(str(error) if isinstance(error, ThemeError) else "Could not import this theme. The current appearance is unchanged.")

    def choose_export(self):
        parent = QFileDialog.getExistingDirectory(self.panel, "Choose a folder for the theme export")
        if not parent:
            return
        identity = self.controller.current.identity
        name = "my-" + identity if identity in BUILTIN_IDS else identity
        destination = Path(parent) / name
        number = 2
        while destination.exists():
            destination = Path(parent) / f"{name}-{number}"
            number += 1
        try:
            export_folder(self.controller.current.package, destination)
            self.status.setText(f"Exported to {destination.name}. Edit theme.json, then use Add theme to import it.")
        except Exception:
            self.status.setText("Could not export the theme. Choose another folder.")
