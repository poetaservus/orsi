"""Presentation-only settings shell; actions remain owned by MainWindow."""
from app.ui.localization import ui_extra, ui_text, QComboBox, QFrame, QLabel, QPushButton, QScrollArea, QWidget

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QKeySequence, QPainter, QShortcut, QPalette
from PySide6.QtWidgets import (QGraphicsBlurEffect, QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QStyle, QStyleOptionButton)
from app.ui.settings_motion import SettingsIconButton, SettingsPageTransition
from app.ui.settings_style import settings_control_style
from app.ui.skill_settings import SkillSettingsPage
from app.ui.image_settings import ImageSettingsPage
from app.ui.notification_settings import NotificationSoundControl, NotificationSwitch
from app.ui.inputs import ScrollSafeComboBox
from app.conversation.personality import PERSONALITIES
from app.conversation.response_language import RESPONSE_LANGUAGES
from app.ui.theme_runtime import apply_theme_style, apply_theme_tree, theme_color
from app.ui.theme_settings import ThemeControls
from app.ui.profile_layout import FeedbackLabel


class _NavigationButton(QPushButton):
    """Retain native single-line painting; wrap long translated section names."""
    def paintEvent(self, event):  # noqa: N802
        if self.fontMetrics().horizontalAdvance(self.text()) <= self.width() - 18:
            super().paintEvent(event)
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        bounds = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)
        painter.setPen(option.palette.color(QPalette.ColorRole.ButtonText))
        painter.drawText(bounds.adjusted(0, 0, -9, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                         self.text())


class SettingsPanel(QFrame):
    settings_font_step = 2
    section_names = ("General", "Models", "Skills", "Image Generation", "Appearance")

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        apply_theme_style(self, _STYLE)
        self.backdrop_blur = None
        self._backdrop_root = None
        self._backdrop_focus = None
        self._root_was_enabled = True
        self._chrome_widgets = ()
        self._close_pending = False
        font = self.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        self.setFont(font)
        outer = QVBoxLayout(self)
        # Reserve the existing native caption band above the unchanged settings layout.
        outer.setContentsMargins(28, 52, 28, 26)
        outer.setSpacing(11)
        escape = QShortcut(QKeySequence("Escape"), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.hide)
        self.header = QWidget(self)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel(ui_text('Settings'))
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title.setObjectName("settingsHeading")
        header.addWidget(title, 1)
        self.close_button = SettingsIconButton(duration=200)
        self.close_button.setObjectName("settingsClose")
        self.close_button.setAccessibleName(ui_text('Close settings'))
        self.close_button.setToolTip(ui_text('Close settings'))
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
        self.navigation_layout = nav
        nav.setSpacing(4)
        self.pages = QStackedWidget()
        self.navigation = []
        self.page_layouts = []
        for index, name in enumerate(self.section_names):
            button = _NavigationButton(ui_text(name))
            button.setToolTip(ui_text(name))
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
        self.page_transition = SettingsPageTransition(self.pages)
        self.pages.currentChanged.connect(lambda i: self.navigation[i].setChecked(True))
        nav.addStretch()
        body.addLayout(nav)
        divider = QFrame()
        divider.setObjectName("settingsDivider")
        divider.setFixedWidth(1)
        body.addWidget(divider)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        parent.theme_controller.changed.connect(self.fit_to_parent)

    def show_section(self, name):
        self.pages.setCurrentIndex(self.section_names.index(name))

    def retranslate_ui(self):
        super().retranslate_ui()
        if not hasattr(self, "navigation"):
            return
        for button in self.navigation:
            button.retranslate_ui()
        self._fit_navigation()

    def _fit_navigation(self):
        width = max(190, max((button.fontMetrics().horizontalAdvance(button.text()) + 24
                             for button in self.navigation), default=190))
        width = min(width, max(190, self.width() // 3))
        for button in self.navigation:
            button.setFixedWidth(width)
            bounds = button.fontMetrics().boundingRect(QRect(0, 0, width - 18, 1000),
                int(Qt.TextFlag.TextWordWrap), button.text())
            button.setFixedHeight(max(42, bounds.height() + 12))

    def add_personal_page(self, page):
        """Installed by the application owner; isolated windows keep their existing tabs."""
        index = self.pages.count()
        self.section_names = (*self.section_names, "Personal profile")
        button = _NavigationButton(ui_text('Personal profile'))
        button.setToolTip(ui_text('Personal profile'))
        button.setObjectName("settingsNavigation")
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setFixedSize(190, 42)
        button.clicked.connect(lambda: self.pages.setCurrentIndex(index))
        self.navigation.append(button)
        self.navigation_layout.insertWidget(self.navigation_layout.count() - 1, button)
        if page.tabbed:
            self.pages.addWidget(page)
            apply_theme_tree(page)
            return
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)
        apply_theme_tree(page)

    def populate(self, window):
        general, models, skills, images, appearance = self.page_layouts
        self.future_settings = {}
        self._heading(general, ui_text('General'), ui_text('Everyday preferences for O.R.S.I.'))
        greeting_row = QFrame()
        greeting_row.setObjectName("settingRow")
        greeting_layout = QVBoxLayout(greeting_row)
        greeting_layout.setContentsMargins(0, 12, 0, 14)
        greeting_layout.setSpacing(6)
        greeting_label = QLabel(ui_text('Greeting'))
        greeting_label.setObjectName("settingName")
        greeting_label.setBuddy(window.greeting_input)
        greeting_layout.addWidget(greeting_label)
        window.greeting_input.setAccessibleName(ui_text('Greeting message'))
        window.greeting_input.setAccessibleDescription(ui_text('Your welcome message'))
        window.greeting_input.setToolTip(ui_text('Your welcome message'))
        window.greeting_input.setPlaceholderText(ui_text('Enter your welcome message'))
        window.greeting_input.setMinimumWidth(0)
        window.greeting_input.setFixedHeight(42)
        window.greeting_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        greeting_layout.addWidget(window.greeting_input)
        general.addWidget(greeting_row)
        window.personality_selector = ScrollSafeComboBox()
        window.personality_selector.setAccessibleName(ui_text('Personality'))
        for personality in PERSONALITIES:
            window.personality_selector.addItem(personality.name, personality.id)
        window.personality_hint = QLabel()
        window.personality_hint.setTextFormat(Qt.TextFormat.PlainText)
        window.personality_hint.setObjectName("settingsDescription")
        window.personality_hint.setWordWrap(True)
        self._row(general, ui_text('Personality'), ui_text("O.R.S.I.'s voice · Remembered for this profile"),
                  window.personality_selector)
        general.addWidget(window.personality_hint)
        window.personality_selector.currentIndexChanged.connect(window._select_personality)
        window._sync_personality_selector()
        window.response_language_selector = ScrollSafeComboBox()
        window.response_language_selector.setAccessibleName(ui_text('Response Language'))
        window.response_language_selector.setAccessibleDescription(
            ui_text('Auto follows the language of your request. A selected language applies from the next response.'))
        window.response_language_selector.use_description_as_tooltip()
        for language in RESPONSE_LANGUAGES:
            window.response_language_selector.addItem(ui_extra("Auto") if language.code == "auto" else language.label, language.code)
        self._row(general, ui_text('Response Language'), ui_text('Auto follows your request · Remembered for this profile'),
                  window.response_language_selector)
        window.response_language_hint = QLabel()
        window.response_language_hint.setObjectName("settingsDescription")
        window.response_language_hint.setWordWrap(True)
        general.addWidget(window.response_language_hint)
        window.response_language_selector.currentIndexChanged.connect(window._select_response_language)
        window._sync_response_language_selector()
        window.tool_approval_toggle = NotificationSwitch(self)
        window.tool_approval_toggle.setAccessibleName(ui_text('Tool execution approval'))
        window.tool_approval_toggle.setAccessibleDescription(
            ui_text('On: review tool changes before they run. Off: run them automatically. Applies to the next tool request; a pending review still needs a decision.'))
        window.tool_approval_toggle.use_description_as_tooltip()
        window.tool_approval_toggle.setChecked(window._tool_approval_required)
        window.tool_approval_toggle.toggled.connect(window._set_tool_approval_required)
        self._row(general, ui_text('Tool execution approval'), ui_text('Review tool changes before they run'),
                  window.tool_approval_toggle, control_size=(44, 24))
        window.notification_toggle = NotificationSwitch(self)
        window.notification_toggle.setAccessibleName(ui_text('Notifications'))
        window.notification_toggle.setChecked(window.notifications.enabled)
        window.notification_toggle.toggled.connect(
            lambda enabled: window.notifications.configure(enabled=enabled))
        self._row(general, ui_text('Notifications'), ui_text('Alerts while O.R.S.I is in the background'),
                  window.notification_toggle, control_size=(44, 24))
        window.notification_sound = NotificationSoundControl(window.notifications, self)
        self._row(general, ui_text('Notification sound'), ui_text('Choose your alert sound'),
                  window.notification_sound, control_size=(196, 36))
        # Keep runtime status available to its owner without a technical footer.
        window.activity.setParent(self)
        window.activity.hide()
        general.addStretch()

        self._heading(models, ui_text('Models'), ui_text('Choose where O.R.S.I runs and which model it uses.'))
        window.model_selector.setAccessibleName(ui_text('Mode'))
        self._row(models, ui_text('Mode'), ui_text('Local or cloud inference'), window.model_selector)
        window.local_model_row = self._row(models, window.local_model_label,
            ui_text('Choose a local BALOGH SYSTEM WORKS model.'), window.local_model_selector)
        models.addWidget(window.local_model_details)
        window.cloud_model_row = self._row(models, window.cloud_model_label,
            ui_text('Choose your cloud model.'), window.cloud_model_selector)
        models.addWidget(window.cloud_model_details)
        models.addStretch()

        self._heading(skills, ui_text('Skills'), ui_text('Preview, install and manage skills here.'))
        window.skill_settings_page = SkillSettingsPage(window.service)
        window.skill_settings_page.catalog_changed.connect(window._skills_changed)
        window.skill_settings_page.close_requested.connect(self.hide)
        window.skill_settings_page.busy_changed.connect(window._settings_worker_busy)
        window.skill_settings_page.idle.connect(window._settings_worker_idle)
        if getattr(window.service, "skill_registry", None) is None:
            hint = QLabel(ui_text('Skill management is unavailable in this session.'))
            hint.setObjectName("settingsDescription")
            hint.setWordWrap(True)
            skills.addWidget(hint)
        skills.addWidget(window.skill_settings_page)
        skills.addStretch()

        self._heading(images, ui_text('Image Generation'), ui_text('Preferences for your next generated image.'))
        self.image_hint = FeedbackLabel()
        self.image_hint.setObjectName("settingsDescription")
        self.image_hint.setWordWrap(True)
        images.addWidget(self.image_hint)
        cloud = getattr(window.inference, "cloud", window.inference)
        window.image_settings_page = ImageSettingsPage(
            getattr(cloud, "image_settings", None), getattr(window.service, "select_image_settings", None))
        images.addWidget(window.image_settings_page)
        images.addSpacing(24)
        self._future(images, "Transparent background", ui_text('Export images without a background'))
        images.addStretch()

        self._heading(appearance, ui_text('Appearance'), ui_text('Display and accessibility preferences.'))
        self.theme_controls = ThemeControls(self, window, appearance)
        window.gui_language_selector = ScrollSafeComboBox()
        window.gui_language_selector.setAccessibleName(ui_text("GUI Language"))
        window.gui_language_selector.setAccessibleDescription(ui_text(
            "Changes interface text immediately. Auto follows your system language. Response Language is independent."))
        window.gui_language_selector.use_description_as_tooltip()
        for language in RESPONSE_LANGUAGES:
            label = ui_text("Auto (system language)") if language.code == "auto" else language.label
            window.gui_language_selector.addItem(label, language.code)
        self._row(appearance, ui_text('GUI Language'), ui_text('Interface display language · Remembered for this profile'), window.gui_language_selector)
        window.gui_language_hint = FeedbackLabel()
        window.gui_language_hint.setObjectName("settingsDescription")
        window.gui_language_hint.setWordWrap(True)
        appearance.addWidget(window.gui_language_hint)
        window.gui_language_selector.currentIndexChanged.connect(window._select_gui_language)
        window._sync_gui_language_selector()
        self._future(appearance, "Text size", ui_text('Adjust interface text size'))
        self._future(appearance, "Reduced motion", ui_text('Limit interface animations'))
        self._future(appearance, "High contrast", ui_text('Increase contrast for easier reading'))
        appearance.addStretch()

    def _future(self, layout, name, description):
        selector = self._placeholder(name)
        self.future_settings[name] = selector
        self._row(layout, ui_text(name), ui_text("{description} · Coming soon", description=description), selector)

    @staticmethod
    def _placeholder(name):
        selector = ScrollSafeComboBox()
        selector.addItem(ui_text('Coming soon'))
        selector.setEnabled(False)
        selector.setAccessibleName(ui_text(name))
        selector.setAccessibleDescription(ui_text('Placeholder. This setting is not implemented.'))
        selector.setToolTip(ui_text('Coming soon. This setting is not implemented.'))
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
    def _row(layout, title, hint, control, *, indent=0, separator=True,
             control_size=(240, 36)):
        row = QFrame()
        row.setObjectName("settingRow" if separator else "settingRowPlain")
        horizontal = QHBoxLayout(row)
        horizontal.setContentsMargins(indent, 12, 0, 12)
        horizontal.setSpacing(12)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        label = title if isinstance(title, QLabel) else QLabel(title)
        label.setObjectName("settingName")
        label.setWordWrap(True)
        labels.addWidget(label)
        if not control.accessibleDescription():
            control.setAccessibleDescription(hint)
        if not control.toolTip():
            control.setToolTip(hint)
        horizontal.addLayout(labels, 1)
        if isinstance(control, QComboBox):
            control.setFixedSize(control_size[0], 36)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(1)
        else:
            control.setFixedSize(*control_size)
        control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        horizontal.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        label.setBuddy(control)
        layout.addWidget(row)
        return row

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        tint = theme_color(self, "#090c15", "settings_bottom")
        tint.setAlpha(160)
        painter.fillRect(self.rect(), tint)

    def fit_to_parent(self):
        parent = self.parentWidget()
        step = 1 if parent.width() < 900 else 2
        if self.settings_font_step != step:
            self.settings_font_step = step
            apply_theme_tree(self)
        self.setGeometry(parent.rect())
        self._fit_navigation()
        for widget, _ in self._chrome_widgets:
            widget.raise_()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        owner = self.parentWidget()
        self.fit_to_parent()
        if self._backdrop_root is not None:
            return
        root = owner._root
        self._backdrop_focus = owner.focusWidget()
        self._root_was_enabled = root.isEnabled()
        self._chrome_widgets = tuple((widget, widget.parentWidget())
                                     for widget in (owner.drag_strip, owner.window_controls))
        # Keep the same window-control instances sharp and active above the blur.
        for widget, _ in self._chrome_widgets:
            widget.setParent(self)
            widget.show()
            widget.raise_()
        owner._position_overlays()
        self._backdrop_root = root
        if root.graphicsEffect() is None:
            self.backdrop_blur = QGraphicsBlurEffect(root)
            self.backdrop_blur.setBlurRadius(18)
            self.backdrop_blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
            root.setGraphicsEffect(self.backdrop_blur)
        # The chat is behind a full-window view; keyboard focus must stay in Settings.
        root.setEnabled(False)
        self.navigation[self.pages.currentIndex()].setFocus()

    def _release_backdrop(self):
        root, self._backdrop_root = self._backdrop_root, None
        if root is None:
            return
        if self.backdrop_blur is not None and root.graphicsEffect() is self.backdrop_blur:
            root.setGraphicsEffect(None)
        self.backdrop_blur = None
        for widget, parent in self._chrome_widgets:
            widget.setParent(parent)
            widget.show()
        self._chrome_widgets = ()
        root.setEnabled(self._root_was_enabled)
        owner = self.parentWidget()
        owner._position_overlays()
        focus, self._backdrop_focus = self._backdrop_focus, None
        if focus is not None and not getattr(owner, "_closing", False):
            try:
                if focus.isVisible() and focus.isEnabled():
                    focus.setFocus()
            except RuntimeError:
                pass  # A profile transition may already have destroyed its editor.

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
        self._release_backdrop()
        super().hideEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "navigation"):
            self._fit_navigation()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)


_STYLE = settings_control_style("QFrame#settingsPanel") + """
QFrame#settingsPanel {
    background: transparent; border: none; border-radius: 0;
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
QFrame#settingsDivider { background: rgba(214, 214, 214, 42); border: none; }
QFrame#settingRow { background: transparent; border: none; border-bottom: 1px solid rgba(214, 214, 214, 42); }
QFrame#settingRowPlain { background: transparent; border: none; }
QFrame#settingsPanel QPushButton#settingsNavigation { text-align: left; padding-left: 9px; font-size: 20px;
    border: none; border-radius: 5px; background: transparent; }
QFrame#settingsPanel QPushButton#settingsNavigation:checked, QFrame#settingsPanel QPushButton#settingsNavigation:hover { background: rgba(185, 197, 213, 17); }
QFrame#settingsPanel QPushButton#settingsClose { background: transparent; border: none; border-radius: 5px; padding: 0; }
QFrame#settingsPanel QPushButton#settingsClose:hover { background: rgba(255,255,255,18); }
QFrame#settingsPanel QPushButton#settingsClose:pressed { background: rgba(255,255,255,30); }
QFrame#settingsPanel QPushButton#notificationPreview { padding: 0; }
QFrame#settingsPanel QWidget#notificationSoundControl QComboBox { padding-right: 8px; }
QWidget#skillSettingsPage, QWidget#imageSettingsPage { background: transparent; }
QWidget#skillSettingsPage QLabel, QWidget#imageSettingsPage QLabel { font-size: 14px; }
QFrame#settingsPanel QLineEdit#greetingInput,
QWidget#skillSettingsPage QLineEdit { min-height: 24px; }
QFrame#settingsPanel QScrollBar:vertical { width: 5px; background: transparent; }
QFrame#settingsPanel QScrollBar::handle:vertical { background: #657385; border-radius: 2px; min-height: 24px; }
QFrame#settingsPanel QScrollBar::add-line:vertical, QFrame#settingsPanel QScrollBar::sub-line:vertical { height: 0; }
QFrame#settingsPanel QScrollBar::add-page:vertical, QFrame#settingsPanel QScrollBar::sub-page:vertical { background: transparent; }
"""
