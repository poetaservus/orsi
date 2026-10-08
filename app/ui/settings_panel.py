"""Presentation-only settings shell; actions remain owned by MainWindow."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)


class ApprovalPlaceholder(QCheckBox):
    """Unavailable setting, painted as the switch in the reference layout."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(44, 24)
        self.setAccessibleName("Tool execution approval")
        self.setAccessibleDescription("Placeholder. Approval preferences are not implemented.")
        self.setToolTip("Coming soon. Existing tool approval rules still apply.")
        self.setEnabled(False)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#343b48"))
        painter.drawRoundedRect(0, 3, 44, 18, 9, 9)
        painter.setBrush(QColor("#a7adb7"))
        painter.drawRoundedRect(3, 5, 14, 14, 5, 5)


class SettingsPanel(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setStyleSheet(_STYLE)
        self.resize(805, 555)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(25, 18, 25, 24)
        outer.setSpacing(10)
        escape = QShortcut(QKeySequence("Escape"), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.hide)
        header = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("settingsHeading")
        header.addWidget(title, 1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("settingsClose")
        self.close_button.setAccessibleName("Close settings")
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header)
        line = QFrame()
        line.setObjectName("settingsDivider")
        line.setFixedHeight(1)
        outer.addWidget(line)
        body = QHBoxLayout()
        body.setSpacing(18)
        nav = QVBoxLayout()
        nav.setSpacing(4)
        self.pages = QStackedWidget()
        self.navigation = []
        self.page_layouts = []
        for index, name in enumerate(("General", "Skills", "Image Generation")):
            button = QPushButton(name)
            button.setObjectName("settingsNavigation")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedSize(155, 32)
            button.clicked.connect(lambda checked=False, i=index: self.pages.setCurrentIndex(i))
            self.navigation.append(button)
            nav.addWidget(button)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            page = QWidget()
            page.setObjectName("settingsPage")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 6, 0)
            layout.setSpacing(0)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
            self.page_layouts.append(layout)
        self.navigation[0].setChecked(True)
        self.pages.currentChanged.connect(lambda i: self.navigation[i].setChecked(True))
        nav.addStretch()
        body.addLayout(nav)
        divider = QFrame()
        divider.setObjectName("settingsDivider")
        divider.setFixedWidth(1)
        body.addWidget(divider)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

    def populate(self, window):
        general, skills, images = self.page_layouts
        self._heading(general, "General Settings", "Core behaviour, model preferences, workflow options")
        window.theme_selector = self._placeholder("Theme")
        self._row(general, "Theme", "Choose how O.R.S.I looks.", window.theme_selector)
        window.tool_approval_toggle = ApprovalPlaceholder()
        self._row(general, "Tool execution approval", "O.R.S.I asks to confirm tool execution. · Coming soon",
                  window.tool_approval_toggle)
        window.model_selector.setAccessibleName("Mode")
        self._row(general, "Mode", "Choose default mode", window.model_selector, separator=False)
        window.local_model_row = self._row(general, window.local_model_label,
            "Choose between local BALOGH SYSTEM WORKS models.", window.local_model_selector, indent=14)
        window.cloud_model_row = self._row(general, window.cloud_model_label,
            "Choose your cloud model.", window.cloud_model_selector, indent=14)
        window.gui_language_selector = self._placeholder("GUI Language")
        self._row(general, "GUI Language", "Interface display language", window.gui_language_selector)
        window.response_language_selector = self._placeholder("Response Language")
        self._row(general, "Response Language",
            "O.R.S.I will respond to you in this language, except when asked otherwise.",
            window.response_language_selector)
        self.more_button = QPushButton("More settings ›")
        self.more_button.setObjectName("settingsMore")
        self.more_button.setCheckable(True)
        general.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.more = QWidget()
        extra = QVBoxLayout(self.more)
        extra.setContentsMargins(0, 0, 0, 0)
        self._row(extra, "Greeting", "Your welcome message", window.greeting_input)
        extra.addWidget(window.local_model_details)
        extra.addWidget(window.cloud_model_details)
        extra.addWidget(window.activity)
        self.more.hide()
        self.more_button.toggled.connect(self.more.setVisible)
        self.more_button.toggled.connect(lambda on: self.more_button.setText("More settings ⌄" if on else "More settings ›"))
        general.addWidget(self.more)
        general.addStretch()
        self._heading(skills, "Skills", "Install, review and manage your O.R.S.I skills.")
        skills.addWidget(window.skills_button, 0, Qt.AlignmentFlag.AlignLeft)
        skills.addStretch()
        self._heading(images, "Image Generation", "Model, size, quality and format for generated images.")
        self.image_hint = QLabel()
        self.image_hint.setObjectName("settingsDescription")
        self.image_hint.setWordWrap(True)
        images.addWidget(self.image_hint)
        images.addSpacing(16)
        images.addWidget(window.image_settings_button, 0, Qt.AlignmentFlag.AlignLeft)
        images.addStretch()

    @staticmethod
    def _placeholder(name):
        selector = QComboBox()
        selector.addItem("Coming soon")
        selector.setEnabled(False)
        selector.setAccessibleName(name)
        selector.setAccessibleDescription("Placeholder. This setting is not implemented.")
        selector.setToolTip("Coming soon. This setting is not implemented.")
        return selector

    @staticmethod
    def _heading(layout, title, hint):
        label = QLabel(title)
        label.setObjectName("settingsSectionTitle")
        layout.addWidget(label)
        description = QLabel(hint)
        description.setObjectName("settingsDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(20)

    @staticmethod
    def _row(layout, title, hint, control, *, indent=0, separator=True):
        row = QFrame()
        row.setObjectName("settingRow" if separator else "settingRowPlain")
        horizontal = QHBoxLayout(row)
        horizontal.setContentsMargins(indent, 7, 0, 8)
        horizontal.setSpacing(12)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        label = title if isinstance(title, QLabel) else QLabel(title)
        label.setObjectName("settingName")
        labels.addWidget(label)
        description = QLabel(hint)
        description.setObjectName("settingsDescription")
        description.setWordWrap(True)
        labels.addWidget(description)
        horizontal.addLayout(labels, 1)
        if isinstance(control, QComboBox):
            control.setFixedSize(168, 26)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(1)
        elif not isinstance(control, ApprovalPlaceholder):
            control.setFixedSize(168, 32)
        if not isinstance(control, ApprovalPlaceholder):
            control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        horizontal.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        label.setBuddy(control)
        layout.addWidget(row)
        return row

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


_STYLE = """
QFrame#settingsPanel {
    background: qlineargradient(x1:0, y1:1, x2:1, y2:0, stop:0 #383b44, stop:1 #3b5066);
    border: 1px solid #48525f; border-radius: 12px;
}
QFrame#settingsPanel QWidget { font-family: Saira; color: #e4e5eb; }
QWidget#settingsPage, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent; border: none;
}
QFrame#settingsPanel QLabel { background: transparent; border: none; }
QLabel#settingsHeading { font-size: 28px; font-weight: 400; }
QLabel#settingsSectionTitle { font-size: 16px; font-weight: 500; }
QLabel#settingName { font-size: 14px; font-weight: 500; }
QLabel#settingsDescription { font-size: 10px; color: #d9dde5; }
QFrame#settingsDivider { background: rgba(207, 214, 227, 42); border: none; }
QFrame#settingRow { background: transparent; border: none; border-bottom: 1px solid rgba(207, 214, 227, 42); }
QFrame#settingRowPlain { background: transparent; border: none; }
QPushButton#settingsNavigation { text-align: left; padding-left: 8px; font-size: 16px;
    border: none; border-radius: 5px; background: transparent; }
QPushButton#settingsNavigation:checked, QPushButton#settingsNavigation:hover { background: rgba(185, 197, 213, 17); }
QPushButton#settingsClose { background: transparent; border: none; font-size: 24px; color: #a5acb6; }
QPushButton#settingsClose:hover { color: white; }
QPushButton#settingsMore { background: transparent; border: none; font-size: 11px; color: #c9ced8; padding: 8px 0; }
QFrame#settingsPanel QComboBox, QFrame#settingsPanel QLineEdit {
    background: #343f50; border: 1px solid #4a5667; border-radius: 4px;
    color: #e4e5eb; font-size: 11px; padding: 1px 6px;
}
QFrame#settingsPanel QComboBox:disabled { color: #9da8b8; }
QFrame#settingsPanel QComboBox::drop-down { width: 20px; border: none; }
QFrame#settingsPanel QComboBox QAbstractItemView { background: #343f50; color: #e4e5eb; selection-background-color: #51627a; }
QFrame#settingsPanel QScrollBar:vertical { width: 5px; background: transparent; }
QFrame#settingsPanel QScrollBar::handle:vertical { background: #657385; border-radius: 2px; min-height: 24px; }
QFrame#settingsPanel QScrollBar::add-line:vertical, QFrame#settingsPanel QScrollBar::sub-line:vertical { height: 0; }
QFrame#settingsPanel QScrollBar::add-page:vertical, QFrame#settingsPanel QScrollBar::sub-page:vertical { background: transparent; }
"""

_CHEVRON = (Path(__file__).with_name("assets") / "settings_chevron.svg").as_posix()
_STYLE += f'QFrame#settingsPanel QComboBox::down-arrow {{ image: url("{_CHEVRON}"); width: 9px; height: 6px; }}'
