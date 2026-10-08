"""Presentation-only settings shell; actions remain owned by MainWindow."""
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from app.ui.settings_motion import SettingsDragStrip, SettingsIconButton
from app.ui.skill_settings import SkillSettingsPage
from app.ui.image_settings import ImageSettingsPage
from app.ui.notification_settings import NotificationSoundControl


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
    preferred_size = QSize(1120, 740)
    section_names = ("General", "Models", "Skills", "Image Generation", "Appearance")

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setStyleSheet(_STYLE)
        self.resize(self.preferred_size)
        self.user_positioned = False
        self._close_pending = False
        font = self.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        self.setFont(font)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 26)
        outer.setSpacing(11)
        escape = QShortcut(QKeySequence("Escape"), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.hide)
        self.drag_strip = SettingsDragStrip(self)
        self.drag_strip.setObjectName("settingsDragStrip")
        self.drag_strip.setAccessibleName("Move settings")
        self.drag_strip.setGeometry(12, 0, self.width() - 24, 18)
        self.header = QWidget(self)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Settings")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title.setObjectName("settingsHeading")
        header.addWidget(title, 1)
        self.close_button = SettingsIconButton(duration=200)
        self.close_button.setObjectName("settingsClose")
        self.close_button.setAccessibleName("Close settings")
        self.close_button.setToolTip("Close settings")
        self.close_button.setCursor(Qt.CursorShape.ArrowCursor)
        self.close_button.setFixedSize(32, 32)
        self.close_button.clicked.connect(self._close_with_feedback)
        self.close_button.pulse_finished.connect(self._finish_close)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.header)
        line = QFrame()
        line.setObjectName("settingsDivider")
        line.setFixedHeight(1)
        outer.addWidget(line)
        body = QHBoxLayout()
        body.setSpacing(20)
        nav = QVBoxLayout()
        nav.setSpacing(4)
        self.pages = QStackedWidget()
        self.navigation = []
        self.page_layouts = []
        for index, name in enumerate(self.section_names):
            button = QPushButton(name)
            button.setObjectName("settingsNavigation")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedSize(190, 42)
            button.clicked.connect(lambda checked=False, i=index: self.pages.setCurrentIndex(i))
            self.navigation.append(button)
            nav.addWidget(button)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
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

    def show_section(self, name):
        self.pages.setCurrentIndex(self.section_names.index(name))

    def populate(self, window):
        general, models, skills, images, appearance = self.page_layouts
        self.future_settings = {}
        self._heading(general, "General", "Everyday preferences for O.R.S.I.")
        greeting_row = QFrame()
        greeting_row.setObjectName("settingRow")
        greeting_layout = QVBoxLayout(greeting_row)
        greeting_layout.setContentsMargins(0, 12, 0, 14)
        greeting_layout.setSpacing(6)
        greeting_label = QLabel("Greeting")
        greeting_label.setObjectName("settingName")
        greeting_label.setBuddy(window.greeting_input)
        greeting_layout.addWidget(greeting_label)
        greeting_description = QLabel("Your welcome message")
        greeting_description.setObjectName("settingsDescription")
        greeting_layout.addWidget(greeting_description)
        window.greeting_input.setAccessibleName("Greeting message")
        window.greeting_input.setPlaceholderText("Enter your welcome message")
        window.greeting_input.setMinimumWidth(0)
        window.greeting_input.setFixedHeight(42)
        window.greeting_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        greeting_layout.addWidget(window.greeting_input)
        general.addWidget(greeting_row)
        window.response_language_selector = self._placeholder("Response Language")
        self._row(general, "Response Language", "Preferred reply language · Coming soon",
                  window.response_language_selector)
        window.tool_approval_toggle = ApprovalPlaceholder()
        self._row(general, "Tool execution approval", "Tool approval preferences · Coming soon",
                  window.tool_approval_toggle)
        window.notification_toggle = QCheckBox("Enable notifications", self)
        window.notification_toggle.setAccessibleName("Notifications")
        window.notification_toggle.setChecked(window.notifications.enabled)
        window.notification_toggle.toggled.connect(
            lambda enabled: window.notifications.configure(enabled=enabled))
        self._stacked_row(general, "Notifications", "Alerts when O.R.S.I is in the background or minimized",
                  window.notification_toggle)
        window.notification_sound = NotificationSoundControl(window.notifications, self)
        self._stacked_row(general, "Notification sound", "Choose a sound for responses, approvals, images and task errors",
                  window.notification_sound)
        general.addSpacing(20)
        general.addWidget(window.activity)
        general.addStretch()

        self._heading(models, "Models", "Choose where O.R.S.I runs and which model it uses.")
        window.model_selector.setAccessibleName("Mode")
        self._row(models, "Mode", "Local or cloud inference", window.model_selector)
        window.local_model_row = self._row(models, window.local_model_label,
            "Choose a local BALOGH SYSTEM WORKS model.", window.local_model_selector)
        models.addWidget(window.local_model_details)
        window.cloud_model_row = self._row(models, window.cloud_model_label,
            "Choose your cloud model.", window.cloud_model_selector)
        models.addWidget(window.cloud_model_details)
        models.addStretch()

        self._heading(skills, "Skills", "Preview, install and manage skills here.")
        window.skill_settings_page = SkillSettingsPage(window.service)
        window.skill_settings_page.catalog_changed.connect(window._skills_changed)
        window.skill_settings_page.close_requested.connect(self.hide)
        window.skill_settings_page.busy_changed.connect(window._settings_worker_busy)
        window.skill_settings_page.idle.connect(window._settings_worker_idle)
        if getattr(window.service, "skill_registry", None) is None:
            hint = QLabel("Skill management is unavailable in this session.")
            hint.setObjectName("settingsDescription")
            hint.setWordWrap(True)
            skills.addWidget(hint)
        skills.addWidget(window.skill_settings_page)
        skills.addStretch()

        self._heading(images, "Image Generation", "Preferences for your next generated image.")
        self.image_hint = QLabel()
        self.image_hint.setObjectName("settingsDescription")
        self.image_hint.setWordWrap(True)
        images.addWidget(self.image_hint)
        images.addSpacing(20)
        cloud = getattr(window.inference, "cloud", window.inference)
        window.image_settings_page = ImageSettingsPage(
            getattr(cloud, "image_settings", None), getattr(window.service, "select_image_settings", None))
        images.addWidget(window.image_settings_page)
        images.addSpacing(24)
        self._future(images, "Transparent background", "Export images without a background")
        images.addStretch()

        self._heading(appearance, "Appearance", "Display and accessibility preferences.")
        window.theme_selector = self._placeholder("Theme")
        self._row(appearance, "Theme", "Choose how O.R.S.I looks · Coming soon", window.theme_selector)
        window.gui_language_selector = self._placeholder("GUI Language")
        self._row(appearance, "GUI Language", "Interface display language · Coming soon", window.gui_language_selector)
        self._future(appearance, "Text size", "Adjust interface text size")
        self._future(appearance, "Reduced motion", "Limit interface animations")
        self._future(appearance, "High contrast", "Increase contrast for easier reading")
        appearance.addStretch()

    def _future(self, layout, name, description):
        selector = self._placeholder(name)
        self.future_settings[name] = selector
        self._row(layout, name, description + " · Coming soon", selector)

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
    def _stacked_row(layout, title, hint, control):
        row = QFrame()
        row.setObjectName("settingRow")
        vertical = QVBoxLayout(row)
        vertical.setContentsMargins(0, 12, 0, 14)
        vertical.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("settingName")
        label.setBuddy(control)
        description = QLabel(hint)
        description.setObjectName("settingsDescription")
        description.setWordWrap(True)
        vertical.addWidget(label)
        vertical.addWidget(description)
        control.setMinimumWidth(0)
        control.setFixedHeight(40)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        vertical.addWidget(control)
        layout.addWidget(row)
        return row

    @staticmethod
    def _row(layout, title, hint, control, *, indent=0, separator=True):
        row = QFrame()
        row.setObjectName("settingRow" if separator else "settingRowPlain")
        horizontal = QHBoxLayout(row)
        horizontal.setContentsMargins(indent, 12, 0, 12)
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
            control.setFixedSize(240, 40)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(1)
        elif not isinstance(control, ApprovalPlaceholder):
            control.setFixedSize(240, 40)
        if not isinstance(control, ApprovalPlaceholder):
            control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        horizontal.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        label.setBuddy(control)
        layout.addWidget(row)
        return row

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(self.rect().bottomLeft(), self.rect().topRight())
        gradient.setColorAt(0, QColor("#383b44"))
        gradient.setColorAt(1, QColor("#3b5066"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#48525f"), 1.0))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)

    def bounded_position(self, position):
        parent = self.parentWidget()
        return QPoint(max(8, min(position.x(), parent.width() - self.width() - 8)),
                      max(44, min(position.y(), parent.height() - self.height() - 8)))

    def fit_to_parent(self):
        parent = self.parentWidget()
        self.resize(min(self.preferred_size.width(), parent.width() - 32),
                    min(self.preferred_size.height(), parent.height() - 64))
        position = self.pos() if self.user_positioned else QPoint(
            (parent.width() - self.width()) // 2, (parent.height() - self.height()) // 2)
        self.move(self.bounded_position(position))

    def _close_with_feedback(self):
        if not self._close_pending:
            self._close_pending = True
            self.close_button.pulse()

    def _finish_close(self):
        if self._close_pending:
            self.hide()

    def hideEvent(self, event):  # noqa: N802
        self._close_pending = False
        self.close_button.reset()
        self.drag_strip._drag_offset = None
        self.drag_strip.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hideEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "drag_strip"):
            self.drag_strip.setGeometry(12, 0, max(0, self.width() - 24), 18)
            self.drag_strip.raise_()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


_STYLE = """
QFrame#settingsPanel {
    background: transparent; border: none; border-radius: 16px;
}
QFrame#settingsPanel QWidget { font-family: Saira; color: #e4e5eb; }
QWidget#settingsPage, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent; border: none;
}
QFrame#settingsPanel QLabel { background: transparent; border: none; }
QLabel#settingsHeading { font-size: 34px; font-weight: 400; }
QLabel#settingsSectionTitle { font-size: 20px; font-weight: 500; }
QLabel#settingName { font-size: 18px; font-weight: 500; }
QFrame#settingsPanel QLabel#conversationStatus { font-size: 14px; color: #d9dde5; }
QFrame#settingsPanel QLabel#settingsLabel, QLabel#settingsDescription { font-size: 14px; color: #d9dde5; }
QFrame#settingsDivider { background: rgba(207, 214, 227, 42); border: none; }
QFrame#settingRow { background: transparent; border: none; border-bottom: 1px solid rgba(207, 214, 227, 42); }
QFrame#settingRowPlain { background: transparent; border: none; }
QPushButton#settingsNavigation { text-align: left; padding-left: 9px; font-size: 20px;
    border: none; border-radius: 5px; background: transparent; }
QPushButton#settingsNavigation:checked, QPushButton#settingsNavigation:hover { background: rgba(185, 197, 213, 17); }
QPushButton#settingsClose { background: transparent; border: none; border-radius: 5px; }
QPushButton#settingsClose:hover { background: rgba(255,255,255,18); }
QPushButton#settingsClose:pressed { background: rgba(255,255,255,30); }
QPushButton#settingsMore { background: transparent; border: none; font-size: 14px; color: #c9ced8; padding: 9px 0; }
QPushButton#settingsMore:hover { color: white; }
QFrame#settingsPanel QComboBox, QFrame#settingsPanel QLineEdit {
    background: #343f50; border: 1px solid #4a5667; border-radius: 4px;
    color: #e4e5eb; font-size: 14px; padding: 1px 6px;
}
QFrame#settingsPanel QPushButton#notificationPreview {
    background: #343f50; border: 1px solid #4a5667; border-radius: 4px;
}
QFrame#settingsPanel QPushButton#notificationPreview:hover { background: #51627a; }
QFrame#settingsPanel QPushButton#notificationPreview:disabled { background: #343f50; }
QWidget#skillSettingsPage, QWidget#imageSettingsPage { background: transparent; }
QWidget#skillSettingsPage QLabel, QWidget#imageSettingsPage QLabel { font-size: 14px; }
QFrame#settingsPanel QLineEdit#greetingInput,
QWidget#skillSettingsPage QLineEdit, QWidget#skillSettingsPage QListWidget {
    background: #343f50; color: #e4e5eb; border: 1px solid #4a5667;
    border-radius: 6px; padding: 8px; font-size: 14px;
}
QFrame#settingsPanel QLineEdit#greetingInput,
QWidget#skillSettingsPage QLineEdit { min-height: 24px; }
QWidget#skillSettingsPage QListWidget::item { padding: 6px; }
QWidget#skillSettingsPage QListWidget::item:selected { background: #51627a; }
QWidget#skillSettingsPage QPushButton, QWidget#imageSettingsPage QPushButton {
    color: #e4e5eb; background: #343f50; border: 1px solid #4a5667;
    border-radius: 6px; padding: 8px 12px; font-size: 14px;
}
QWidget#skillSettingsPage QPushButton:hover, QWidget#imageSettingsPage QPushButton:hover { background: #51627a; }
QWidget#skillSettingsPage QPushButton:disabled, QWidget#imageSettingsPage QPushButton:disabled { color: #9da8b8; }
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
