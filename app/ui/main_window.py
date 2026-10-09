from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QFileDialog,
    QGraphicsBlurEffect,
    QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.security.host_access import HostReadScope
from app.inference.engine import InferenceUnavailable
from app.inference.attachments import AttachmentError
from app.inference.completion import CompletionText
from app.ui.approvals import create_inline_approval
from app.ui.chat import ChatView
from app.ui.context_window import ContextWindowBar
from app.ui.status import ConversationStatus
from app.ui.worker import ConversationWorker, ModelSwitchWorker
from app.ui.skill_picker import SkillPicker
from app.ui.settings_panel import SettingsPanel
from app.ui.notifications import NotificationManager
from app.ui.settings_motion import SettingsIconButton
from app.ui.window_frame import CAPTION_HEIGHT, DragStrip, WindowControls, WindowsFrame
from app.ui.attachments import AttachmentTray
from app.ui.image_viewer import ImageViewer
from app.ui.motion import create_attachment_file_dialog
from app.ui.composer import (
    ComposerFrame, MessageInput, COMPOSER_STYLE, composer_tools, configure_input, configure_send,
    COMPOSER_WIDTH as _COMPOSER_WIDTH, COMPOSER_HEIGHT as _COMPOSER_HEIGHT,
)
from app.conversation.attachment_processing import SUPPORTED_FILE_FILTER


log = logging.getLogger(__name__)


_ICON_DIRECTORY = Path(__file__).with_name("assets")
_FONT_DIRECTORY = _ICON_DIRECTORY / "fonts"
_TOP_BUTTON_WIDTH = 32
_TOP_BUTTON_HEIGHT = 28
_TOP_ICON_SIZE = 22
_CHAT_TOP_INSET = 44
_COMPOSER_BOTTOM_MARGIN = 42
_DEFAULT_GREETING_TEXT = "Lets Roll."
_GREETING_MAX_LENGTH = 80
_STARTUP_GREETING_HEIGHT = 64
_STARTUP_GREETING_GAP = 24
_STARTUP_TRANSITION_MS = 340
_APPROVAL_TRANSITION_MS = 240
_BOTTOM_GLASS_BLUR_RADIUS = 18.0
_BOTTOM_GLASS_BLUR_PADDING = 80
_BOTTOM_GLASS_TOP_FEATHER = 34
_MIDDLE_PANEL_WIDTH = 1120
_BACKGROUND_TOP_CROP = 68
_FONT_LOADED = False
_UI_FONT_FAMILY = ""


def _normalize_greeting_message(value: object) -> str:
    if not isinstance(value, str):
        return _DEFAULT_GREETING_TEXT
    message = " ".join(value.split())
    if not message:
        return _DEFAULT_GREETING_TEXT
    return message[:_GREETING_MAX_LENGTH]


def _load_ui_font() -> None:
    global _FONT_LOADED, _UI_FONT_FAMILY
    if not _FONT_LOADED:
        _FONT_LOADED = True
        font_path = _FONT_DIRECTORY / "Saira.ttf"
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _UI_FONT_FAMILY = families[0]
    if _UI_FONT_FAMILY:
        font = QFont(_UI_FONT_FAMILY)
        font.setWeight(QFont.Weight.Normal)
        app = QApplication.instance()
        if app is not None:
            app.setFont(font)


def _apply_ui_font(widget: QWidget) -> None:
    if not _UI_FONT_FAMILY:
        return
    font = widget.font()
    font.setFamily(_UI_FONT_FAMILY)
    font.setWeight(QFont.Weight.Normal)
    widget.setFont(font)


def _apply_greeting_font(widget: QWidget) -> None:
    _apply_ui_font(widget)
    font = widget.font()
    font.setWeight(QFont.Weight.Light)
    widget.setFont(font)


class BottomGlassPane(QWidget):
    """Invisible bottom lens that blurs transcript content behind it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)
        self._backdrop_surface = None
        self._chat_view = None

    def set_backdrop_widgets(self, surface: QWidget, chat_view: ChatView) -> None:
        self._backdrop_surface = surface
        self._chat_view = chat_view

    def backdrop_widgets(self) -> tuple[QWidget | None, ChatView | None]:
        return self._backdrop_surface, self._chat_view

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        backdrop = self._blurred_backdrop()
        if backdrop.isNull():
            return
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), backdrop)

    def _blurred_backdrop(self) -> QPixmap:
        surface = self._backdrop_surface
        chat_view = self._chat_view
        if surface is None or chat_view is None or self.width() <= 0 or self.height() <= 0:
            return QPixmap()

        backdrop = QPixmap(self.size())
        backdrop.fill(Qt.GlobalColor.transparent)
        source_in_surface = self.geometry()
        chat_content = chat_view.widget()
        if chat_content is None:
            return backdrop

        content_top_left = chat_content.mapTo(surface, QPoint(0, 0))
        content_rect = QRect(content_top_left, chat_content.size())
        overlap = source_in_surface.intersected(content_rect)
        if overlap.isEmpty():
            return backdrop

        target_rect = QRect(
            overlap.topLeft() - source_in_surface.topLeft(),
            overlap.size(),
        )
        render_background = getattr(surface, "paint_background_region", None)
        if callable(render_background):
            background_painter = QPainter(backdrop)
            render_background(background_painter, QRectF(target_rect), QRectF(overlap))
            background_painter.end()
        else:
            surface.render(
                backdrop,
                target_rect.topLeft() - overlap.topLeft(),
                QRegion(overlap),
                QWidget.RenderFlag.DrawWindowBackground,
            )

        chat_source = QRect(
            overlap.x() - content_rect.x(),
            overlap.y() - content_rect.y(),
            overlap.width(),
            overlap.height(),
        )
        blur_bounds = QRect(QPoint(0, 0), chat_content.size())
        expanded_source = chat_source.adjusted(
            -_BOTTOM_GLASS_BLUR_PADDING,
            -_BOTTOM_GLASS_BLUR_PADDING,
            _BOTTOM_GLASS_BLUR_PADDING,
            _BOTTOM_GLASS_BLUR_PADDING,
        ).intersected(blur_bounds)
        blurred_fragment = self._soften(chat_content.grab(expanded_source))
        fragment_offset = chat_source.topLeft() - expanded_source.topLeft()
        chat_fragment = blurred_fragment.copy(QRect(fragment_offset, chat_source.size()))
        text_painter = QPainter(backdrop)
        text_painter.drawPixmap(target_rect.topLeft(), chat_fragment)
        text_painter.end()
        return self._feather_top(backdrop)

    @staticmethod
    def _feather_top(pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap
        fade_height = min(_BOTTOM_GLASS_TOP_FEATHER, pixmap.height())
        if fade_height <= 1:
            return pixmap
        mask = QLinearGradient(0, 0, 0, fade_height)
        mask.setColorAt(0.0, QColor(255, 255, 255, 0))
        mask.setColorAt(0.38, QColor(255, 255, 255, 90))
        mask.setColorAt(1.0, QColor(255, 255, 255, 255))
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(QRectF(0, 0, pixmap.width(), fade_height), mask)
        painter.fillRect(
            QRectF(0, fade_height, pixmap.width(), pixmap.height() - fade_height),
            QColor(255, 255, 255, 255),
        )
        painter.end()
        return pixmap

    @staticmethod
    def _soften(pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap

        scene = QGraphicsScene()
        scene.setSceneRect(QRectF(pixmap.rect()))

        item = QGraphicsPixmapItem(pixmap)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(_BOTTOM_GLASS_BLUR_RADIUS)
        blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        item.setGraphicsEffect(blur)
        scene.addItem(item)

        softened = QPixmap(pixmap.size())
        softened.fill(Qt.GlobalColor.transparent)
        painter = QPainter(softened)
        scene.render(painter, QRectF(softened.rect()), QRectF(pixmap.rect()))
        painter.end()
        return softened


class ChatSurface(QWidget):
    """Paint the quiet gradient and centered conversation panel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("mainContent")
        self._background = QPixmap(str(_ICON_DIRECTORY / "o.r.s.i_gui_bck.png"))

    def middle_panel_rect(self) -> QRect:
        width = min(_MIDDLE_PANEL_WIDTH, max(0, self.width()))
        x = max(0, (self.width() - width) // 2)
        return QRect(x, 0, width, self.height())

    def paint_background_region(
        self,
        painter: QPainter,
        target: QRectF,
        source: QRectF,
    ) -> None:
        if self._background.isNull():
            gradient = QLinearGradient(
                target.left() - source.left(),
                target.top(),
                target.left() - source.left() + max(1, self.width()),
                target.top(),
            )
            gradient.setColorAt(0.0, QColor("#131517"))
            gradient.setColorAt(0.55, QColor("#111315"))
            gradient.setColorAt(1.0, QColor("#101214"))
            painter.fillRect(target, gradient)
            return

        source_y = min(_BACKGROUND_TOP_CROP, max(0, self._background.height() - 1))
        full_background = QRectF(
            0,
            source_y,
            self._background.width(),
            max(1, self._background.height() - source_y),
        )
        width_ratio = full_background.width() / max(1, self.width())
        height_ratio = full_background.height() / max(1, self.height())
        background_source = QRectF(
            full_background.left() + source.left() * width_ratio,
            full_background.top() + source.top() * height_ratio,
            source.width() * width_ratio,
            source.height() * height_ratio,
        )
        painter.drawPixmap(target, self._background, background_source)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        self.paint_background_region(painter, QRectF(self.rect()), QRectF(self.rect()))


class MainWindow(QMainWindow):
    approval_requested = Signal(object)

    def __init__(
        self,
        service,
        hostname: str,
        startup_error: str | None = None,
        inference=None,
        preferences_store=None,
    ):
        super().__init__()
        _load_ui_font()
        del hostname
        self.service = service
        self.setAcceptDrops(True)
        self.inference = inference
        self.startup_error = startup_error
        self._preferences_store = preferences_store
        self._greeting_message = self._load_greeting_message()
        self._tool_approval_required = self._load_tool_approval_required()
        configure_approval = getattr(service, "set_tool_approval_required", None)
        if callable(configure_approval):
            configure_approval(self._tool_approval_required)
        self.notifications = NotificationManager(self, preferences_store)
        self.thread = None
        self._settings_busy = False
        self._image_viewer = None
        self._attachment_picker = None
        self._pending_image_reply = None
        self._image_request_draft = None
        self._image_in_flight = False
        self._image_stopping = False
        self.worker = None
        self._active_user_message_band = None
        self._approval_panel = None
        self._approval_transition = None
        self.approval_requested.connect(self._show_approval, Qt.ConnectionType.QueuedConnection)
        bind_approval = getattr(service, "set_approval_requester", None)
        if callable(bind_approval):
            bind_approval(self.approval_requested.emit)

        self.setObjectName("mainWindow")
        self.setWindowTitle("O.R.S.I")
        self._window_frame = WindowsFrame(self)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint)
        self.resize(1280, 800)
        self.setMinimumSize(760, 600)

        root = QWidget()
        self._root = root
        root.setObjectName("root")
        root.installEventFilter(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.drag_strip = DragStrip(root)
        self.window_controls = WindowControls(self, root)

        self.app_controls = QWidget(root)
        self.app_controls.setObjectName("appControls")
        controls_layout = QHBoxLayout(self.app_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self.new_session_button = QPushButton()
        self.new_session_button.setObjectName("topBarButton")
        self.new_session_button.setFixedSize(_TOP_BUTTON_WIDTH, _TOP_BUTTON_HEIGHT)
        self.new_session_button.setIcon(QIcon(str(_ICON_DIRECTORY / "top_new_session.svg")))
        self.new_session_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.new_session_button.setToolTip("New session — permanently clears this conversation")
        self.new_session_button.setAccessibleName("New session")
        self.new_session_button.setEnabled(service is not None)

        self.settings_button = SettingsIconButton(svg=_ICON_DIRECTORY / "top_settings.svg")
        self.settings_button.setObjectName("topBarButton")
        self.settings_button.setFixedSize(_TOP_BUTTON_WIDTH, _TOP_BUTTON_HEIGHT)
        self.settings_button.setIcon(QIcon(str(_ICON_DIRECTORY / "top_settings.svg")))
        self.settings_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")

        controls_layout.addWidget(self.new_session_button)
        self.app_controls_separator = QFrame(self.app_controls)
        self.app_controls_separator.setObjectName("appControlsSeparator")
        self.app_controls_separator.setFixedSize(1, 14)
        self.app_controls_separator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        controls_layout.addWidget(self.app_controls_separator, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addWidget(self.settings_button)
        self.app_controls.setFixedSize(2 * _TOP_BUTTON_WIDTH + 13, _TOP_BUTTON_HEIGHT)
        self.context_window = ContextWindowBar(
            int(getattr(inference, "context_length", 0)),
            root,
        )
        self.context_window.setFixedHeight(_TOP_BUTTON_HEIGHT)

        content = ChatSurface()
        self._content = content
        content.installEventFilter(self)
        content_layout = QVBoxLayout(content)
        self._content_layout = content_layout
        content_layout.setContentsMargins(0, _CHAT_TOP_INSET, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        attachment_store = getattr(getattr(service, "store", None), "attachment_store", None)
        self.chat = ChatView(attachment_store=attachment_store)
        self.chat.image_activated.connect(self._open_image_viewer)
        content_layout.addWidget(self.chat, 1)

        self.settings_panel = SettingsPanel(root)

        self.model_selector = QComboBox()
        self.model_selector.setObjectName("modelSelector")
        self.model_selector.setFixedHeight(38)
        if inference is None:
            self.model_selector.addItem("Local", "local")
            self.model_selector.setEnabled(False)
        else:
            for mode in inference.available_modes:
                label = "Local"
                if mode == "cloud":
                    label = f"Cloud · {inference.cloud_provider_name}"
                self.model_selector.addItem(label, mode)
            self._sync_inference_selector()
            self.model_selector.currentIndexChanged.connect(self._select_inference_mode)

        self.local_model_label = QLabel("Local Model")
        self.local_model_label.setObjectName("settingsLabel")
        self.local_model_selector = QComboBox()
        self.local_model_selector.setObjectName("modelSelector")
        self.local_model_selector.setAccessibleName("Local model")
        self.local_model_selector.setFixedHeight(38)
        self.local_model_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.local_model_selector.setMinimumContentsLength(20)
        catalog = getattr(inference, "model_catalog", None)
        for model in getattr(catalog, "models", ()):
            label = f"Experimental · {model.name}" if model.text_only else model.name
            self.local_model_selector.addItem(label, model.id)
            self.local_model_selector.setItemData(
                self.local_model_selector.count() - 1,
                f"{model.path.name}\n{model.compatibility_note}",
                Qt.ItemDataRole.ToolTipRole,
            )
        if self.local_model_selector.count() == 0:
            self.local_model_selector.addItem("No supported local models found", None)
        self.local_model_details = QLabel()
        self.local_model_details.setObjectName("settingsLabel")
        self.local_model_details.setWordWrap(True)
        self.local_model_details.setMinimumHeight(36)
        self.local_model_selector.currentIndexChanged.connect(self._select_local_model)

        self.cloud_model_label = QLabel("Cloud Model")
        self.cloud_model_label.setObjectName("settingsLabel")
        self.cloud_model_selector = QComboBox()
        self.cloud_model_selector.setObjectName("modelSelector")
        self.cloud_model_selector.setAccessibleName("Cloud model")
        self.cloud_model_selector.setFixedHeight(38)
        cloud_catalog = getattr(inference, "cloud_model_catalog", None)
        for profile in getattr(getattr(cloud_catalog, "config", None), "profiles", ()):
            label = {"gpt-6-luna": "GPT-6 Luna", "gpt-6.1-sol": "GPT-6.1 Sol"}.get(profile.id, profile.id)
            self.cloud_model_selector.addItem(label, profile.id)
        self.cloud_model_details = QLabel()
        self.cloud_model_details.setObjectName("settingsLabel")
        self.cloud_model_details.setWordWrap(True)
        self.cloud_model_selector.currentIndexChanged.connect(self._select_cloud_model)

        self.greeting_input = QLineEdit()
        self.greeting_input.setObjectName("greetingInput")
        self.greeting_input.setFixedHeight(38)
        self.greeting_input.setMaxLength(_GREETING_MAX_LENGTH)
        self.greeting_input.setText(self._greeting_message)

        self.activity = ConversationStatus(
            self._ready_status() if not startup_error else "Model unavailable"
        )
        self.settings_panel.populate(self)
        self._sync_local_model_selector()
        self._sync_cloud_model_selector()
        self.settings_panel.hide()

        self.bottom_glass = BottomGlassPane(content)
        self.bottom_glass.setObjectName("bottomGlass")
        self.bottom_glass.set_backdrop_widgets(content, self.chat)

        self.startup_greeting = QLabel(self._greeting_message, content)
        self.startup_greeting.setObjectName("startupGreeting")
        self.startup_greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.startup_greeting.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.startup_greeting_opacity = QGraphicsOpacityEffect(self.startup_greeting)
        self.startup_greeting_opacity.setOpacity(1.0)
        self.startup_greeting.setGraphicsEffect(self.startup_greeting_opacity)

        self.composer = ComposerFrame(content)
        self.composer.setObjectName("composer")
        self.composer.setFixedHeight(_COMPOSER_HEIGHT)
        self._composer_stack = QStackedLayout(self.composer)
        self._composer_stack.setContentsMargins(0, 0, 0, 0)
        self._message_composer = QWidget(self.composer)
        self._message_composer.setObjectName("messageComposer")
        self._composer_stack.addWidget(self._message_composer)
        message_layout = QVBoxLayout(self._message_composer)
        message_layout.setContentsMargins(0, 0, 0, 0)
        message_layout.setSpacing(0)
        store = getattr(getattr(service, "store", None), "attachment_store", None)
        self.attachment_tray = AttachmentTray(store, lambda: getattr(self.inference, "mode", "local"), self._message_composer)
        message_layout.addWidget(self.attachment_tray)
        self.attachment_hint = QLabel(self._message_composer)
        self.attachment_hint.setObjectName("attachmentHint")
        self.attachment_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.attachment_hint.setFixedHeight(26)
        self.attachment_hint.hide()
        message_layout.addWidget(self.attachment_hint)
        composer_row = QWidget(self._message_composer)
        composer_row.setFixedHeight(_COMPOSER_HEIGHT)
        message_layout.addWidget(composer_row)
        composer_layout = QHBoxLayout(composer_row)
        composer_layout.setContentsMargins(22, 7, 20, 7)
        composer_layout.setSpacing(6)
        composer_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)

        self.composer_tools, self.add_placeholder, self.folder_placeholder = composer_tools(self._message_composer)

        self.input = MessageInput()
        configure_input(self.input)

        self.action_slot = QWidget()
        self.action_slot.setObjectName("composerActionSlot")
        self.action_slot.setFixedSize(34, 37)

        self.send = QPushButton(self.action_slot)
        configure_send(self.send)
        self.send.move(0, 4)

        self.stop = QPushButton(self.action_slot)
        self.stop.setObjectName("stopButton")
        self.stop.setFixedSize(34, 34)
        self.stop.move(0, 4)
        self.stop.setIcon(QIcon(str(_ICON_DIRECTORY / "stop.svg")))
        self.stop.setIconSize(QSize(14, 14))
        self.stop.setToolTip("Stop")
        self.stop.setAccessibleName("Stop")
        self.stop.setEnabled(False)
        self.stop.hide()

        composer_layout.addWidget(self.composer_tools, 0, Qt.AlignmentFlag.AlignVCenter)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)
        input_layout.addWidget(self.input, 1)
        composer_layout.addLayout(input_layout, 1)
        composer_layout.addWidget(self.action_slot)
        self.skill_picker = SkillPicker(self.input, self.composer,
                                        getattr(service, "skill_registry", None),
                                        input_layout=input_layout, send_button=self.send)

        self.setCentralWidget(root)
        self.setStyleSheet(_STYLE)
        _apply_ui_font(self.input)
        self.send.clicked.connect(self.submit)
        self.stop.clicked.connect(self.cancel_current_task)
        self.new_session_button.clicked.connect(self.create_new_session)
        self.settings_button.clicked.connect(self._toggle_settings)
        self.input.submit_requested.connect(self.submit)
        self.add_placeholder.clicked.connect(self._pick_attachments)
        self.add_placeholder.setEnabled(store is not None)
        self.input.attachments_requested.connect(self.attachment_tray.add_mime)
        self.attachment_tray.changed.connect(self._refresh_attachment_composer)
        self.attachment_tray.notice.connect(self._attachment_notice)
        self.attachment_tray.idle.connect(self._attachment_idle)
        self.chat.verticalScrollBar().valueChanged.connect(self.bottom_glass.update)
        self.chat.verticalScrollBar().rangeChanged.connect(lambda *_: self.bottom_glass.update())
        self._greeting_save_timer = QTimer(self)
        self._greeting_save_timer.setSingleShot(True)
        self._greeting_save_timer.timeout.connect(self._save_greeting_message)
        self.greeting_input.textChanged.connect(self._greeting_text_changed)
        self.greeting_input.editingFinished.connect(self._finish_greeting_edit)
        self._intro_active = not startup_error and not self._agent_error()
        self._intro_transition = None
        _apply_greeting_font(self.startup_greeting)
        visible_history = getattr(getattr(service, "store", None), "visible_messages", None)
        if callable(visible_history):
            for message in visible_history():
                value = CompletionText(message.content, message.completion,
                    tuple(message.completion_history) if message.completion_history else None)
                self.chat.add_message("User" if message.role == "user" else "Agent", value, message.stopped,
                    skill_name=getattr(message, "skill_name", None), attachments=getattr(message, "attachments", ()),
                    images=getattr(message, "generated_images", ()))
            if self.chat._messages:
                self._intro_active = False
        self._update_context_window()
        self._position_overlays()
        if startup_error:
            self.chat.add_message("Agent", startup_error, True)
        elif self._agent_error():
            self.chat.add_message("Agent", self._agent_error(), True)

    def bind_profile(self, session):
        self._profile_session = session
        unregister = session.register(stop=self._stop_profile_view, drain=self._drain_profile_view,
                                      clear=self._clear_profile_view)
        self.destroyed.connect(unregister)

    def _stop_profile_view(self):
        if QThread.currentThread() != QWidget.thread(self):
            raise RuntimeError("Close the personal profile on the interface thread.")
        self._closing = True
        self.hide()
        self.setEnabled(False)
        self.skill_settings_page.revoke_profile()
        self._greeting_save_timer.stop()
        self.attachment_tray.shutdown()
        for dialog in (self._attachment_picker, self._image_viewer, self._approval_panel):
            if dialog is not None:
                dialog.reject()

    def _drain_profile_view(self):
        for thread in (self.thread, self.attachment_tray.thread, self.skill_settings_page.thread):
            if thread is not None and thread.isRunning():
                thread.quit()
                if not thread.wait(30000):
                    raise RuntimeError("Profile work is still stopping.")

    def _clear_profile_view(self):
        self._preferences_store = None
        self.chat.clear_messages()
        self.input.clear()
        self.greeting_input.clear()
        self.startup_greeting.clear()
        self._greeting_message = ""
        self._image_request_draft = None
        self._greeting_save_timer.stop()
        self.skill_settings_page.prepared = None
        self.skill_settings_page.source.clear()
        self.skill_settings_page.installed.clear()
        self.settings_panel.hide()
        self.notifications.shutdown()
        self.notification_sound.shutdown()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._position_overlays()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._window_frame.configure()

    def nativeEvent(self, event_type, message):  # noqa: N802
        frame = getattr(self, "_window_frame", None)
        if frame is not None:
            handled, result = frame.handle(message)
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "window_controls"):
            self.window_controls.refresh()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name
        if watched in {
            getattr(self, "_root", None),
            getattr(self, "_content", None),
        } and event.type() == QEvent.Type.Resize:
            self._position_overlays()
        return super().eventFilter(watched, event)

    def _load_tool_approval_required(self) -> bool:
        try:
            payload = self._preferences_store.load({}) if self._preferences_store is not None else {}
            value = payload.get("tool_approval_required", True) if isinstance(payload, dict) else True
            return value if type(value) is bool else True
        except Exception:
            log.warning("Tool approval preferences could not be loaded.")
            return True

    def _set_tool_approval_required(self, required: bool) -> None:
        configure = getattr(self.service, "set_tool_approval_required", None)
        if callable(configure):
            configure(required)
        self._tool_approval_required = required
        if self.thread is None:
            self.activity.set_activity(self._ready_status())
        if self._preferences_store is not None:
            try:
                payload = self._preferences_store.load({})
                if not isinstance(payload, dict):
                    raise ValueError("Invalid UI preferences")
                payload["tool_approval_required"] = required
                self._preferences_store.save(payload)
            except Exception:
                # Preserve unreadable preferences instead of replacing user settings.
                log.warning("Tool approval preferences could not be saved.")

    def _load_greeting_message(self) -> str:
        store = self._preferences_store
        if store is None:
            return _DEFAULT_GREETING_TEXT
        try:
            payload = store.load({})
        except Exception:
            log.warning("UI preferences could not be loaded.", exc_info=True)
            return _DEFAULT_GREETING_TEXT
        if not isinstance(payload, dict):
            return _DEFAULT_GREETING_TEXT
        return _normalize_greeting_message(payload.get("greeting_message"))

    def _save_greeting_message(self) -> None:
        store = self._preferences_store
        if store is None:
            return
        try:
            payload = store.load({})
        except Exception:
            log.warning("UI preferences could not be loaded before saving.", exc_info=True)
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["greeting_message"] = self._greeting_message
        try:
            store.save(payload)
        except Exception:
            log.warning("UI preferences could not be saved.", exc_info=True)

    def _greeting_text_changed(self, text: str) -> None:
        self._greeting_message = _normalize_greeting_message(text)
        self.startup_greeting.setText(self._greeting_message)
        if self._preferences_store is not None:
            self._greeting_save_timer.start(450)

    def _finish_greeting_edit(self) -> None:
        normalized = _normalize_greeting_message(self.greeting_input.text())
        if self.greeting_input.text() != normalized:
            self.greeting_input.setText(normalized)
        self._greeting_message = normalized
        self.startup_greeting.setText(normalized)
        if self._greeting_save_timer.isActive():
            self._greeting_save_timer.stop()
        self._save_greeting_message()

    def _position_overlays(self) -> None:
        if not hasattr(self, "composer"):
            return
        content = self.composer.parentWidget()
        target = self._composer_target_geometry()
        glass_y = max(0, target.y())
        self.bottom_glass.setGeometry(
            0,
            glass_y,
            content.width(),
            content.height() - glass_y,
        )
        if self._intro_transition is None:
            self.composer.setGeometry(target)
        self._position_startup_greeting(target)
        self.bottom_glass.raise_()
        self.startup_greeting.raise_()
        self.composer.raise_()
        self.skill_picker.reposition()
        self.drag_strip.setGeometry(7, 7,
            max(0, self._root.width() - self.window_controls.width() - 16), CAPTION_HEIGHT - 7)
        self.drag_strip.raise_()
        self.app_controls.move(8, 8)
        self.app_controls.raise_()
        self.context_window.move((self._root.width() - self.context_window.width()) // 2, 8)
        self.context_window.raise_()
        self.window_controls.move(self._root.width() - self.window_controls.width() - 8, 8)
        self.window_controls.raise_()
        self.settings_panel.fit_to_parent()
        if self.settings_panel.isVisible():
            self.settings_panel.raise_()

    def _composer_target_geometry(self) -> QRect:
        content = self.composer.parentWidget()
        width = min(_COMPOSER_WIDTH, max(320, content.width() - 32))
        x = max(16, (content.width() - width) // 2)
        height = self.composer.height()
        if self._intro_active:
            y = max(24, (content.height() - height) // 2)
        else:
            y = max(16, content.height() - _COMPOSER_BOTTOM_MARGIN - height)
        return QRect(x, y, width, height)

    def _position_startup_greeting(self, composer_geometry: QRect) -> None:
        content = self.composer.parentWidget()
        width = min(760, max(320, content.width() - 64))
        x = max(16, (content.width() - width) // 2)
        y = max(24, composer_geometry.y() - _STARTUP_GREETING_GAP - _STARTUP_GREETING_HEIGHT)
        self.startup_greeting.setGeometry(x, y, width, _STARTUP_GREETING_HEIGHT)
        self.startup_greeting.setVisible(self._intro_active or self._intro_transition is not None)

    def _leave_intro_mode(self) -> None:
        if not self._intro_active:
            return
        if self._intro_transition is not None:
            self._intro_transition.stop()
            self._intro_transition.deleteLater()
            self._intro_transition = None
        self._intro_active = False
        target = self._composer_target_geometry()
        self._position_startup_greeting(self.composer.geometry())
        self.startup_greeting.show()
        self.bottom_glass.setGeometry(
            0,
            max(0, target.y()),
            self._content.width(),
            self._content.height() - max(0, target.y()),
        )

        group = QParallelAnimationGroup(self)
        geometry = QPropertyAnimation(self.composer, b"geometry", group)
        geometry.setDuration(_STARTUP_TRANSITION_MS)
        geometry.setStartValue(self.composer.geometry())
        geometry.setEndValue(target)
        geometry.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(geometry)

        opacity = QPropertyAnimation(self.startup_greeting_opacity, b"opacity", group)
        opacity.setDuration(max(180, _STARTUP_TRANSITION_MS - 70))
        opacity.setStartValue(self.startup_greeting_opacity.opacity())
        opacity.setEndValue(0.0)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(opacity)

        def finish() -> None:
            self._intro_transition = None
            self.composer.setGeometry(self._composer_target_geometry())
            self.startup_greeting.hide()
            self.startup_greeting_opacity.setOpacity(0.0)
            group.deleteLater()

        group.finished.connect(finish)
        self._intro_transition = group
        group.start()

    def _activate_intro_mode(self) -> None:
        self._animate_composer_height(_COMPOSER_HEIGHT, animated=False)
        if self._intro_transition is not None:
            self._intro_transition.stop()
            self._intro_transition.deleteLater()
            self._intro_transition = None
        self._intro_active = True
        target = self._composer_target_geometry()
        self._position_startup_greeting(target)
        self.startup_greeting.show()
        self.startup_greeting.raise_()
        self.composer.raise_()
        if not self.isVisible():
            self.startup_greeting_opacity.setOpacity(1.0)
            self._position_overlays()
            return

        self.bottom_glass.setGeometry(
            0,
            max(0, target.y()),
            self._content.width(),
            self._content.height() - max(0, target.y()),
        )
        group = QParallelAnimationGroup(self)
        geometry = QPropertyAnimation(self.composer, b"geometry", group)
        geometry.setDuration(_STARTUP_TRANSITION_MS)
        geometry.setStartValue(self.composer.geometry())
        geometry.setEndValue(target)
        geometry.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(geometry)

        opacity = QPropertyAnimation(self.startup_greeting_opacity, b"opacity", group)
        opacity.setDuration(_STARTUP_TRANSITION_MS)
        opacity.setStartValue(0.0)
        opacity.setEndValue(1.0)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(opacity)

        def finish() -> None:
            self._intro_transition = None
            self.composer.setGeometry(self._composer_target_geometry())
            self._position_startup_greeting(self.composer.geometry())
            self.startup_greeting_opacity.setOpacity(1.0)
            group.deleteLater()

        self.startup_greeting_opacity.setOpacity(0.0)
        group.finished.connect(finish)
        self._intro_transition = group
        group.start()

    @Slot()
    def _toggle_settings(self) -> None:
        visible = not self.settings_panel.isVisible()
        self.settings_panel.setVisible(visible)
        if visible:
            self.settings_button.pulse(180.0)
            self.settings_panel.raise_()
            self.settings_panel.navigation[self.settings_panel.pages.currentIndex()].setFocus()

    def _manage_skills(self) -> None:
        self.settings_panel.show_section("Skills")
        self.settings_panel.show()
        self.settings_panel.raise_()

    def _settings_worker_busy(self, busy):
        self._settings_busy = busy
        available = not busy and self.thread is None and not getattr(self, "_closing", False)
        self.send.setEnabled(available)
        self.input.setEnabled(available)
        self.new_session_button.setEnabled(available and self.service is not None)
        self.model_selector.setEnabled(available and self.inference is not None)
        self._sync_local_model_selector()
        self._sync_cloud_model_selector()

    def _settings_worker_idle(self):
        if getattr(self, "_closing", False):
            QTimer.singleShot(0, self.close)

    def _pick_attachments(self):
        if self.thread is not None or self.attachment_tray.store is None:
            return
        if self._attachment_picker is not None:
            self._attachment_picker.raise_()
            return
        dialog = create_attachment_file_dialog(self, cloud=getattr(self.inference, "mode", "local") == "cloud",
                                               name_filter=SUPPORTED_FILE_FILTER)
        self._attachment_picker = dialog

        def finished(result):
            self._attachment_picker = None
            if result == QFileDialog.DialogCode.Accepted and not getattr(self, "_closing", False):
                self.attachment_tray.add_paths(dialog.selectedFiles())
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.open()

    def _open_image_viewer(self, references, index):
        if getattr(self, "_closing", False):
            return
        if self._image_viewer is not None:
            self._image_viewer.raise_()
            return
        viewer = ImageViewer(self.attachment_tray.store, references, index,
                             cloud=getattr(self.inference, "mode", "local") == "cloud", parent=self)
        self._image_viewer = viewer
        viewer.set_reply_available(self.thread is None and self.service is not None)
        viewer.reply_requested.connect(self._reply_from_image_viewer)
        viewer.finished.connect(self._image_viewer_closed)
        viewer.show()

    def _image_viewer_closed(self, *_):
        # Closing during preparation cancels automatic submission. The staged
        # prompt remains in the main composer for an explicit manual retry.
        self._pending_image_reply = None
        self._image_viewer = None

    def _reply_from_image_viewer(self, references, prompt):
        viewer = self._image_viewer
        if viewer is None or getattr(self, "_closing", False):
            return
        if self.thread is not None or self.attachment_tray.is_processing:
            viewer.status.setText("Wait for the current operation to finish.")
            return
        if self.input.toPlainText().strip() or self.attachment_tray.count:
            viewer.status.setText("Your main composer has a draft. Close this viewer to finish it, or clear it before sending.")
            return
        viewer.set_preparing()
        self._pending_image_reply = viewer
        self.input.setPlainText(prompt)
        self.attachment_tray.add_references(references)
        if not self.attachment_tray.is_processing:
            self._attachment_idle()

    def _message_composer_height(self):
        return _COMPOSER_HEIGHT + (76 if self.attachment_tray.count else 0) + (26 if not self.attachment_hint.isHidden() else 0)

    def _refresh_attachment_composer(self):
        if not self.attachment_tray.count:
            self.attachment_hint.hide()
        height = self._message_composer_height()
        if self._approval_panel is None and self.composer.height() != height:
            self._animate_composer_height(height, animated=False)

    def _attachment_notice(self, text):
        self.attachment_hint.setToolTip(text)
        self.attachment_hint.setText(self.attachment_hint.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, max(150, self.composer.width() - 44)))
        self.attachment_hint.show()
        if self._approval_panel is None:
            self._animate_composer_height(self._message_composer_height(), animated=False)

    def _attachment_idle(self):
        if getattr(self, "_closing", False):
            self.close()
            return
        viewer = self._pending_image_reply
        if viewer is not None:
            self._pending_image_reply = None
            # The established send path handles model support, API readiness,
            # admission, draft recovery and manual skill selection.
            viewer.accept()
            if self.attachment_tray.count and self.attachment_tray.ready:
                self.submit()

    def dragEnterEvent(self, event):  # noqa: N802
        mime = event.mimeData()
        if self.thread is None and self.attachment_tray.store is not None and (
                mime.hasImage() or mime.hasUrls() and all(u.isLocalFile() for u in mime.urls())):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # noqa: N802
        if self.thread is None and self.attachment_tray.store is not None:
            self.attachment_tray.add_mime(event.mimeData())
            event.acceptProposedAction()
        else:
            event.ignore()

    def _skills_changed(self) -> None:
        name = self.skill_picker.selected_name
        if name is not None and self.service.skill_registry.get(name) is None:
            self.skill_picker.clear_selection()
        self._update_context_window()

    def submit(self) -> None:
        if self.thread is None and self.skill_picker.accept_current():
            return
        message = self.input.toPlainText().strip()
        attachments = self.attachment_tray.references
        if (not message and not self.attachment_tray.count) or self.thread is not None or self._settings_busy:
            return
        if self.attachment_tray.count:
            if not self.attachment_tray.ready:
                self._attachment_notice("Wait for preparation, remove failed attachments, or keep only one attachment in local mode.")
                return
            # Do this before clearing text/skill/draft or asking for an API key.
            try:
                admit = getattr(self.service, "_admit_attachments", None)
                if not callable(admit):
                    raise ValueError("Image and file sending is not enabled for this model yet.")
                admit(attachments)
            except AttachmentError as exc:
                self._attachment_notice(str(exc))
                return
            except Exception:
                self._attachment_notice("Attachments are ready. Sending images and files will be available in the next updates.")
                return
        if self.startup_error:
            self.chat.add_message("Agent", self.startup_error, True)
            return
        if self.inference is not None and self.inference.mode == "cloud" and not self._ensure_cloud_ready():
            return

        skill_name = self.skill_picker.selected_name
        self._image_request_draft = (self.input.toPlainText(), attachments)
        check_image = getattr(self.service, "will_generate_images", None)
        self._image_in_flight = bool(callable(check_image) and
            check_image(message, attachments=attachments, skill_name=skill_name))
        self._image_stopping = False
        self._submitted_draft = (self.input.toPlainText(), skill_name) if attachments else None
        self.skill_picker.clear_selection()
        self.input.clear()
        self._leave_intro_mode()
        self._active_user_message_band = self.chat.add_message("User", message, attachments=attachments)
        if not attachments or getattr(self.service, 'supports_admission_reporting', False) is not True:
            self.attachment_tray.clear()
        self._set_busy(True)
        self.thread = QThread()
        self.worker = ConversationWorker(self.service, message, skill_name=skill_name, attachments=attachments)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._worker_succeeded)
        self.worker.failed.connect(self._worker_failed)
        self.worker.activity.connect(self._set_working_activity)
        self.worker.text_updated.connect(self._stream_preview)
        self.worker.skill_used.connect(self._set_user_message_skill)
        self.worker.admitted.connect(self._attachment_admitted)
        self.worker.draft_rejected.connect(self._restore_attachment_draft)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot()
    def _attachment_admitted(self):
        self._submitted_draft = None
        self.attachment_tray.clear()

    @Slot()
    def _restore_attachment_draft(self):
        submitted = getattr(self, '_submitted_draft', None)
        if submitted is None or getattr(self, '_closing', False):
            return
        message, skill_name = submitted
        self.input.setPlainText(message)
        if skill_name is not None:
            self.skill_picker.select_name(skill_name)
        self.chat.remove_message(self._active_user_message_band)
        self._active_user_message_band = None
        self._submitted_draft = None

    @Slot(object)
    def _show_approval(self, record) -> None:
        if self._approval_panel is not None:
            self.service.resolve_approval(record.approval_id, False)
            return
        panel = create_inline_approval(
            self.composer, self.service, record, self._approval_finished,
        )
        if panel is None:
            return
        self._approval_panel = panel
        # A fast tool call can arrive during the intro animation. Finish it before
        # expanding the composer so its old geometry cannot overwrite the review.
        if self._intro_transition is not None:
            self._intro_transition.stop()
            self._intro_transition.deleteLater()
            self._intro_transition = None
        self._intro_active = False
        self.startup_greeting.hide()
        self.settings_panel.hide()
        self.skill_picker.popup.hide()
        height = 154 if record.capability == "filesystem.mkdir" else 280
        # Reveal the review at its natural size instead of squeezing its text
        # fields into thin strips while the outer composer is growing.
        panel.setMinimumHeight(height)
        self._composer_stack.addWidget(panel)
        self._composer_stack.setCurrentWidget(panel)
        self._animate_composer_height(height)
        panel.setFocus()
        self._set_working_activity("Waiting for your approval…")
        self.notifications.notify("approval")

    def _approval_finished(self) -> None:
        panel = self._approval_panel
        self._approval_panel = None
        if panel is not None:
            self._composer_stack.removeWidget(panel)
            panel.hide()
        self._composer_stack.setCurrentWidget(self._message_composer)
        self._animate_composer_height(self._message_composer_height())
        if self.input.isEnabled():
            self.input.setFocus()

    def _animate_composer_height(self, height: int, *, animated: bool = True) -> None:
        if self._approval_transition is not None:
            self._approval_transition.stop()
            self._approval_transition.deleteLater()
            self._approval_transition = None

        def resize(value: int) -> None:
            self.composer.setFixedHeight(value)
            # Recompute the top edge on every frame, keeping the bottom anchored
            # and adapting to window resizes during the transition.
            self._position_overlays()

        if (not animated or not self.isVisible() or getattr(self, "_closing", False)
                or self.composer.height() == height):
            resize(height)
            return
        animation = QVariantAnimation(self)
        animation.setDuration(_APPROVAL_TRANSITION_MS)
        animation.setStartValue(self.composer.height())
        animation.setEndValue(height)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.valueChanged.connect(resize)

        def finish() -> None:
            self._approval_transition = None
            resize(height)
            animation.deleteLater()

        animation.finished.connect(finish)
        self._approval_transition = animation
        self._position_overlays()
        animation.start()

    @Slot(object)
    def _worker_succeeded(self, text: str) -> None:
        self._done(text, False)

    @Slot(str)
    def _stream_preview(self, text: str) -> None:
        if not getattr(self, "_closing", False) and getattr(self, "_preview_active", False):
            self.chat.set_stream_preview(text)

    @Slot(object)
    def _worker_failed(self, text: str) -> None:
        self._done(text, True)

    def _done(self, text: str, error: bool) -> None:
        if getattr(self, "_closing", False):
            return
        duration_seconds = self._set_busy(False)
        images = getattr(text, "generated_images", ())
        cancelled = self._image_stopping or getattr(getattr(text, "completion", None), "finish_reason", None) == "cancelled"
        generation_frame = self.chat.take_generation_frame(images,
            status="Image generation stopped" if cancelled else "Image generation failed" if error else "Image generation stopped")
        if (error or cancelled) and self._image_in_flight and self._image_request_draft is not None:
            prompt, references = self._image_request_draft
            if not self.input.toPlainText().strip():
                self.input.setPlainText(prompt)
            if references and not self.attachment_tray.count:
                self.attachment_tray.add_references(references)
        self._image_in_flight = False
        self._image_stopping = False
        self._image_request_draft = None
        notice = None
        try:
            if self.inference is not None:
                notice = self.inference.consume_notice()
                self._sync_inference_selector()
            self._update_context_window()
        except Exception:
            log.warning("Could not refresh response controls or context meter.")
        self.chat.add_message(
            "Agent",
            text,
            error,
            duration_seconds=duration_seconds,
            images=images,
            generation_frame=generation_frame,
        )
        if notice:
            self.chat.add_message("Agent", notice)
        if not cancelled:
            self.notifications.notify("error" if error else "image" if images else "response")

    @Slot()
    def _thread_finished(self) -> None:
        if self.thread is not None:
            self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self._active_user_message_band = None
        self._set_busy(False)
        if getattr(self, "_closing", False):
            self.close()

    def _set_busy(self, busy: bool) -> float | None:
        if self._image_viewer is not None:
            self._image_viewer.set_reply_available(not busy and self.service is not None)
        self._preview_active = busy
        self.send.setEnabled(not busy and not self._settings_busy)
        self.stop.setEnabled(busy and self.service is not None)
        self.send.setVisible(not busy)
        self.stop.setVisible(busy)
        self.input.setEnabled(not busy and not self._settings_busy)
        self.add_placeholder.setEnabled(not busy and self.attachment_tray.store is not None)
        self.attachment_tray.set_editable(not busy)
        self.model_selector.setEnabled(not busy and not self._settings_busy and self.inference is not None)
        self.local_model_selector.setEnabled(
            not busy and not self._settings_busy and self.service is not None and self.inference is not None
            and self.inference.mode == "local"
            and bool(getattr(getattr(self.inference, "model_catalog", None), "models", ()))
        )
        self.new_session_button.setEnabled(not busy and not self._settings_busy and self.service is not None)
        self.cloud_model_selector.setEnabled(
            not busy and not self._settings_busy and self.service is not None and self.inference is not None
            and self.inference.mode == "cloud"
            and getattr(self.inference, "cloud_model_catalog", None) is not None
        )
        self.skill_settings_page.set_available(not busy and not getattr(self, "_closing", False))
        self._sync_image_settings(busy=busy or self._settings_busy)
        duration_seconds = self.chat.set_thinking(busy)
        self.activity.set_activity("" if busy else self._ready_status())
        return duration_seconds

    def cancel_current_task(self) -> None:
        if self._approval_panel is not None:
            self._approval_panel.reject()
        cancel = getattr(self.service, "cancel_current_task", None)
        if callable(cancel):
            if cancel():
                self._image_stopping = True
            self.stop.setEnabled(False)
            self._set_working_activity("Stopping…")

    @Slot(str)
    def _set_user_message_skill(self, name: str) -> None:
        if self.thread is not None and self._active_user_message_band is not None:
            self.chat.set_message_skill(self._active_user_message_band, name)

    @Slot(str)
    def _set_working_activity(self, text: str) -> None:
        if self.thread is None:
            return
        if text == "Generating image…" and self._image_stopping:
            return
        self.activity.set_activity(text)
        self.chat.set_activity(text)
        if text == "Generating image…":
            self._image_in_flight = True
            cloud = getattr(self.inference, "cloud", self.inference)
            settings = getattr(cloud, "image_settings", None)
            size = settings.current.size if settings is not None else "1024x1024"
            width, height = map(int, size.split("x"))
            self.chat.start_image_generation(width / height)
        elif text == "Stopping…" and self.chat.generation_frame is not None:
            self.chat.generation_frame.stop("Stopping image generation…")

    def create_new_session(self) -> None:
        if self.thread is not None or self._settings_busy:
            return
        if self._image_viewer is not None:
            self._image_viewer.reject()
        reset = getattr(self.service, "new_session", None)
        if not callable(reset):
            return
        try:
            reset()
        except Exception as exc:
            self.chat.add_message("Agent", str(exc), True)
            return
        self.chat.clear_messages()
        self.attachment_tray.clear()
        self.attachment_hint.hide()
        self.skill_picker.clear_selection()
        self.input.clear()
        self._activate_intro_mode()
        self._update_context_window()
        self.activity.set_activity(self._ready_status())
        self.input.setFocus()

    def _ready_status(self) -> str:
        if self._agent_error() and not self._agent_enabled():
            return "Agent unavailable · Chat only"
        if self.inference is None:
            return "Ready · Chat only"
        if self._agent_enabled():
            listing_enabled = self._filesystem_list_enabled()
            find_enabled = self._filesystem_find_enabled()
            text_read_enabled = self._filesystem_read_text_enabled()
            search_enabled = self._filesystem_search_enabled()
            parts = ["Metadata"]
            if find_enabled:
                parts.append("find")
            if listing_enabled:
                parts.append("listing")
            if text_read_enabled:
                parts.append("text")
            if search_enabled:
                parts.append("search")
            read_capabilities = "Metadata only" if parts == ["Metadata"] else " + ".join(parts)
            read_status = (
                f"Full local read · {read_capabilities}"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else f"Portable-root read · {read_capabilities}"
            )
            approval_mode = "approval" if self._tool_approval_required else "automatic"
            if "filesystem.mkdir" in getattr(self.service, "agent_capabilities", ()):
                read_status += f" · Folder {approval_mode}"
            if "filesystem.write_text" in getattr(self.service, "agent_capabilities", ()):
                read_status += f" · Text-write {approval_mode}"
            if "filesystem.edit_text" in getattr(self.service, "agent_capabilities", ()):
                read_status += f" · Text-edit {approval_mode}"
            if "filesystem.copy" in getattr(self.service, "agent_capabilities", ()):
                read_status += f" · Copy {approval_mode}"
            if "filesystem.move" in getattr(self.service, "agent_capabilities", ()):
                read_status += f" · Move {approval_mode}"
            if "filesystem.trash" in getattr(self.service, "agent_capabilities", ()):
                read_status += f" · Trash {approval_mode}"
            if self.inference.mode == "cloud":
                return (
                    f"Cloud key needed · Agent · {read_status}"
                    if not self.inference.cloud_has_api_key
                    else f"Ready · Cloud · Agent · {read_status}"
                )
            return f"Ready · Local · Agent · {read_status}"
        if self.inference.mode == "cloud":
            return (
                "Cloud key needed · Chat only"
                if not self.inference.cloud_has_api_key
                else "Ready · Cloud · Chat only"
            )
        return "Ready · Local · Chat only"

    @Slot(int)
    def _select_inference_mode(self, index: int) -> None:
        if self.inference is None or self._settings_busy or index < 0:
            return
        requested = self.model_selector.itemData(index)
        previous = self.inference.mode
        if requested == "cloud" and not self._ensure_cloud_ready():
            self._sync_inference_selector()
            return
        try:
            self.inference.set_mode(requested)
        except InferenceUnavailable as exc:
            self.chat.add_message("Agent", str(exc), True)
            self.inference.set_mode(previous)
        self._sync_inference_selector()
        self._sync_local_model_selector()
        self._sync_cloud_model_selector()
        self._refresh_attachment_composer()
        if requested == "local" and self.attachment_tray.count > 1:
            self._attachment_notice("Local mode allows one attachment per message. Remove the extra attachments to continue.")
        self._update_context_window()
        self.activity.set_activity(self._ready_status())

    def _sync_cloud_model_selector(self):
        self._sync_image_settings(busy=self.thread is not None or self._settings_busy)
        catalog = getattr(self.inference, "cloud_model_catalog", None)
        available = catalog is not None
        for widget in (self.cloud_model_row, self.cloud_model_label, self.cloud_model_selector, self.cloud_model_details):
            widget.setVisible(available and self.inference.mode == "cloud")
        self.cloud_model_selector.blockSignals(True)
        self.cloud_model_selector.setCurrentIndex(
            self.cloud_model_selector.findData(catalog.current_id) if available else -1
        )
        self.cloud_model_selector.blockSignals(False)
        self.cloud_model_selector.setEnabled(bool(
            available and self.service is not None and self.inference.mode == "cloud"
            and self.thread is None and not self._settings_busy
        ))
        if available:
            profile = catalog.current_profile
            status = "Verified" if profile.qualified else "Verification pending"
            self.cloud_model_details.setText(
                f"{profile.effective_context_length:,} context · {profile.max_output_tokens:,} reply limit\n{status}"
            )

            self.cloud_model_selector.setToolTip(self.cloud_model_details.text())

    def _sync_image_settings(self, *, busy=False):
        cloud = getattr(self.inference, "cloud", self.inference)
        store = getattr(cloud, "image_settings", None)
        apply_settings = getattr(self.service, "select_image_settings", None)
        available = getattr(self.inference, "supports_image_generation", False) is True
        self.image_settings_page.set_context(store, apply_settings, available=available, busy=busy)
        self.settings_panel.image_hint.setText(
            "These preferences apply to your next generated image." if available and store is not None else
            "Image generation is unavailable in the current mode. Choose a supported cloud model in Models.")

    def _open_image_settings(self):
        self.settings_panel.show_section("Image Generation")
        self.settings_panel.show()
        self.settings_panel.raise_()

    def _select_cloud_model(self, index):
        catalog = getattr(self.inference, "cloud_model_catalog", None)
        if self.thread is not None or self._settings_busy or self.service is None or catalog is None or index < 0:
            self._sync_cloud_model_selector()
            return
        requested = self.cloud_model_selector.itemData(index)
        if requested == catalog.current_id:
            return
        try:
            self.service.select_cloud_model(requested)
        except (InferenceUnavailable, RuntimeError, ValueError, OSError):
            self.chat.add_message("Agent", "Could not switch cloud models. Your previous selection is still active.", True)
        self._sync_cloud_model_selector()
        self._update_context_window()
        self.activity.set_activity(self._ready_status())

    def _sync_local_model_selector(self):
        catalog = getattr(self.inference, "model_catalog", None)
        local_mode = self.inference is None or self.inference.mode == "local"
        for widget in (self.local_model_row, self.local_model_label, self.local_model_selector, self.local_model_details):
            widget.setVisible(local_mode)
        self.local_model_selector.blockSignals(True)
        index = self.local_model_selector.findData(catalog.current_id) if catalog else -1
        if index >= 0:
            self.local_model_selector.setCurrentIndex(index)
        elif catalog and catalog.models:
            self.local_model_selector.setCurrentIndex(-1)
        self.local_model_selector.blockSignals(False)
        enabled = bool(catalog and catalog.models and self.service is not None
                       and self.inference.mode == "local" and self.thread is None and not self._settings_busy)
        self.local_model_selector.setEnabled(enabled)
        if catalog:
            config = catalog.current_config
            model = next((item for item in catalog.models if item.id == catalog.current_id), None)
            note = model.compatibility_note if model else "Model unavailable"
            if config.vision is not None:
                note = "Image input available · Experimental file editing"
            self.local_model_details.setText(
                f"{int(config.context_length):,} context · {config.max_tokens:,} reply limit\n"
                f"Settings applied automatically\n{note}"
                if isinstance(config.context_length, int) else "Settings applied automatically"
            )
            self.local_model_details.setToolTip(
                f"Temperature {config.temperature} · Top-p {config.top_p} · Top-k {config.top_k}\n"
                f"{'GPU acceleration' if config.gpu_layers != 0 else 'CPU'} · {config.cache_type.upper()} cache\n"
                "Switching preserves your conversation. Choose the Qwen vision model for image input."
            )
            self.local_model_selector.setToolTip(
                self.local_model_details.text() + "\n" + self.local_model_details.toolTip())
        else:
            self.local_model_details.setText("Local model selection is unavailable.")

    @Slot(int)
    def _select_local_model(self, index):
        if self.thread is not None or self._settings_busy or self.service is None or index < 0:
            return
        catalog = getattr(self.inference, "model_catalog", None)
        requested = self.local_model_selector.itemData(index)
        if catalog is None or requested is None or requested == catalog.current_id:
            return
        self._set_busy(True)
        self.stop.setEnabled(False)
        self.activity.set_activity("Loading local model...")
        self.thread = QThread()
        self.worker = ModelSwitchWorker(self.service, requested)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._local_model_selected)
        self.worker.failed.connect(self._local_model_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.finished.connect(self._sync_local_model_selector)
        self.thread.start()

    @Slot()
    def _local_model_selected(self):
        if getattr(self, "_closing", False):
            return
        self._set_busy(False)
        self._sync_local_model_selector()
        try:
            self._update_context_window()
        except Exception:
            log.warning("Could not refresh context meter after local model selection.")

    @Slot(str)
    def _local_model_failed(self, reason):
        if getattr(self, "_closing", False):
            return
        self._local_model_selected()
        self.chat.add_message("Agent", f"Could not switch models: {reason}\nThe previous selection was kept.", True)

    def _ensure_cloud_ready(self) -> bool:
        if self.inference is None:
            return False
        prepare = getattr(self.inference, "prepare_cloud_credentials", None)
        if callable(prepare):
            prepare()
        if not self.inference.cloud_has_api_key:
            key, accepted = QInputDialog.getText(
                self,
                f"{self.inference.cloud_provider_name} API key",
                "Enter the API key for this session. It will not be saved to the USB drive:",
                QLineEdit.EchoMode.Password,
            )
            if not accepted or not key.strip():
                return False
            self.inference.set_cloud_api_key(key)
        return True

    def _agent_enabled(self) -> bool:
        return bool(getattr(self.service, "agent_enabled", False))

    def _agent_error(self) -> str | None:
        value = getattr(self.service, "agent_error", None)
        return str(value) if value else None

    def _host_read_scope(self) -> HostReadScope | None:
        value = getattr(self.service, "host_read_scope", None)
        try:
            return HostReadScope(value) if value is not None else None
        except ValueError:
            return None

    def _filesystem_list_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.list" in values

    def _filesystem_find_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.find" in values

    def _filesystem_read_text_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.read_text" in values

    def _filesystem_search_enabled(self) -> bool:
        values = getattr(self.service, "agent_capabilities", ())
        return isinstance(values, tuple) and "filesystem.search" in values

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._closing = True
        self.settings_panel.hide()
        self.settings_button.reset()
        if self.skill_settings_page.thread is not None:
            # The embedded page owns its import/install worker. Let its transaction
            # finish and join before shutting down the service or closing its parent.
            self.setEnabled(False)
            event.ignore()
            return
        if self._attachment_picker is not None:
            self._attachment_picker.reject()
        if self._image_viewer is not None:
            self._image_viewer.reject()
        self.attachment_tray.shutdown()
        self.notification_sound.shutdown()
        self.notifications.shutdown()
        self._animate_composer_height(_COMPOSER_HEIGHT, animated=False)
        try:
            if self._greeting_save_timer.isActive():
                self._greeting_save_timer.stop()
                self._save_greeting_message()
            if self._approval_panel is not None:
                self._approval_panel.reject()
        except Exception:
            log.warning("Window settings or approval cleanup failed.")
        finally:
            try:
                shutdown = getattr(self.service, "shutdown", None)
                if callable(shutdown):
                    shutdown()
            except Exception:
                log.warning("Application service cleanup failed.")
            finally:
                close = getattr(self.inference, "close", None)
                try:
                    if callable(close):
                        close()
                except Exception:
                    log.warning("Inference cleanup failed.")
        if self.attachment_tray.is_processing or self.thread is not None and self.thread.isRunning():
            # Let the cancelled worker unwind with Qt's event loop still alive.
            # Never destroy a running QThread or force-terminate a file write.
            self.setEnabled(False)
            if self.thread is not None:
                self.thread.quit()
            event.ignore()
            return
        self.chat.set_thinking(False)
        super().closeEvent(event)

    def _sync_inference_selector(self) -> None:
        if self.inference is None:
            return
        index = self.model_selector.findData(self.inference.mode)
        if index >= 0 and index != self.model_selector.currentIndex():
            self.model_selector.blockSignals(True)
            self.model_selector.setCurrentIndex(index)
            self.model_selector.blockSignals(False)

    def _runtime_mode_label(self) -> str:
        if self.inference is None:
            return "Local"
        return "Cloud" if self.inference.mode == "cloud" else "Local"

    def _update_context_window(self) -> None:
        length = int(getattr(self.inference, "context_length", 0))
        self.context_window.set_runtime_mode(self._runtime_mode_label())
        self.context_window.set_context_length(length)
        budgeter = getattr(self.service, "context_budget", None)
        if callable(budgeter):
            reporter = getattr(self.service, "reported_context_tokens", None)
            self.context_window.set_budget(budgeter(), reported_tokens=reporter() if callable(reporter) else None)
            return
        estimate = getattr(self.service, "estimated_context_tokens", None)
        used = estimate() if callable(estimate) else 0
        self.context_window.set_used_tokens(used)


_STYLE = """
QDialog#folderApproval, QDialog#writeApproval, QDialog#copyApproval, QDialog#moveApproval, QDialog#trashApproval {
    background: #202224;
    color: #ededed;
}
QDialog#folderApproval QLabel, QDialog#writeApproval QLabel, QDialog#copyApproval QLabel, QDialog#moveApproval QLabel, QDialog#trashApproval QLabel {
    color: #dedede;
    font-family: Saira;
    font-size: 13px;
    font-weight: 400;
}
QPlainTextEdit#approvalPath, QPlainTextEdit#approvalContent, QPlainTextEdit#approvalDetails {
    background: #151719;
    color: #f2f2f2;
    border: 1px solid #55595c;
    padding: 8px;
    font-family: Consolas;
    font-size: 14px;
    selection-background-color: #355e7e;
}
QDialog#folderApproval QPushButton, QDialog#writeApproval QPushButton, QDialog#copyApproval QPushButton, QDialog#moveApproval QPushButton, QDialog#trashApproval QPushButton {
    background: #34383b;
    color: #f1f1f1;
    border: 1px solid #64696d;
    border-radius: 4px;
    padding: 7px 15px;
    font-family: Saira;
    font-size: 13px;
    font-weight: 400;
}
QDialog#folderApproval QPushButton:focus, QDialog#writeApproval QPushButton:focus, QDialog#copyApproval QPushButton:focus, QDialog#moveApproval QPushButton:focus, QDialog#trashApproval QPushButton:focus { border: 2px solid #91bfe0; }
QDialog#folderApproval QPushButton:hover, QDialog#writeApproval QPushButton:hover, QDialog#copyApproval QPushButton:hover, QDialog#moveApproval QPushButton:hover, QDialog#trashApproval QPushButton:hover { background: #42484d; }
QMainWindow#mainWindow, QWidget#root {
    background: #050506;
    color: #d7d7d9;
    font-family: Saira;
    font-weight: 400;
}
QWidget#mainContent, QWidget#chatContent { background: transparent; }
QWidget#appControls { background: transparent; border: none; }
QFrame#appControlsSeparator { background: rgba(203, 208, 218, 42); border: none; }
QPushButton#topBarButton {
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 0;
}
QPushButton#topBarButton:hover { background: rgba(255,255,255,18); }
QPushButton#topBarButton:pressed { background: rgba(255,255,255,30); }
QPushButton#topBarButton:disabled { background: transparent; }
QFrame#settingsPanel {
    background: #252627;
    border: 1px solid #3a3b3c;
    border-radius: 15px;
}
QPushButton#manageSkillsButton {
    color: #d9dce3; background: #303640; border: 1px solid rgba(153, 165, 184, 36);
    border-radius: 6px; padding: 7px 12px; font-family: Saira; font-size: 14px;
}
QPushButton#manageSkillsButton:hover { background: #3e4551; }
QPushButton#manageSkillsButton:disabled { color: #767d89; }
QLabel#settingsTitle {
    color: #e1e1e1;
    background: transparent;
    border: none;
    font-size: 16px;
    font-weight: 400;
}
QLabel#settingsLabel {
    color: #a8a8a8;
    background: transparent;
    border: none;
    font-size: 12px;
    font-weight: 400;
}
QWidget#contextWindow { background: transparent; }
QLabel#contextStatusLine {
    color: #d6d4d4;
    background: transparent;
    border: none;
    font-family: Saira;
    font-size: 15px;
    font-weight: 400;
}
QLabel#contextWindowTitle, QLabel#contextWindowSize {
    color: #a8a8a8;
    background: transparent;
    font-size: 11px;
}
QLabel#contextWindowSize { color: #dedede; }
QProgressBar#contextWindowBar {
    background: #303030;
    border: none;
    border-radius: 2px;
}
QProgressBar#contextWindowBar::chunk {
    background: #d4d4d4;
    border-radius: 2px;
}
QLabel#startupGreeting {
    color: #e7e8ed;
    background: transparent;
    border: none;
    font-family: Saira;
    font-size: 34px;
    font-weight: 300;
}
QScrollArea#chatView { background: transparent; border: none; }
QScrollArea#chatView QWidget#qt_scrollarea_viewport { background: transparent; }
QFrame#userMessage {
    background: transparent;
    border: none;
    border-radius: 12px;
}
QFrame#orsiMessage, QFrame#errorMessage { background: transparent; border: none; }
QFrame#userMessage QLabel, QFrame#orsiMessage QLabel, QFrame#orsiMessage QTextEdit#messageText, QLabel#streamPreview {
    color: #e3e3e4;
    font-family: Saira;
    font-size: 18px;
    font-weight: 400;
}
QFrame#userMessage QLabel { color: #dce2ee; font-size: 12.5pt; }
QFrame#errorMessage QLabel, QFrame#errorMessage QTextEdit#messageText {
    color: #ff8d86;
    font-family: Saira;
    font-size: 15px;
    font-weight: 400;
}
QWidget#messageMetaRow, QWidget#messageActionRow {
    background: transparent;
    border: none;
}
QLabel#responseTiming, QLabel#userSkill {
    color: #858791;
    background: transparent;
    border: none;
    font-family: Saira;
    font-size: 11px;
    font-weight: 400;
}
QLabel#workingActivity {
    color: #b5b8c2;
    background: transparent;
    border: none;
    padding: 0;
    font-family: Saira;
    font-size: 12px;
    font-weight: 400;
}
QFrame#orsiMessage QLabel#incompleteResponse, QFrame#errorMessage QLabel#incompleteResponse {
    color: #e9bd78;
    background: transparent;
    border: none;
    font-family: Saira;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#copyMessageButton {
    color: #b7b8bd;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0;
    font-family: Saira;
    font-size: 11px;
    font-weight: 400;
}
QPushButton#copyMessageButton:hover { color: #ededee; background: #292a30; }
QPushButton#copyMessageButton:pressed { background: #1e1f24; }
QFrame#codeBlock, QFrame#skillPicker {
    background: #20242d;
    border: 1px solid rgba(153, 165, 184, 36);
    border-radius: 12px;
}
QWidget#codeHeader, QWidget#skillPickerHeader {
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(153, 165, 184, 25);
}
QLabel#codeLanguage, QLabel#skillPickerTitle {
    color: #b9bfcc;
    background: transparent;
    border: none;
    font-size: 12px;
    font-family: Saira;
    font-weight: 400;
}
QPushButton#copyCodeButton {
    color: #e3e3e4;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0;
    font-size: 11px;
    font-family: Saira;
    font-weight: 400;
}
QPushButton#copyCodeButton:hover { background: rgba(255, 255, 255, 8); }
QPushButton#copyCodeButton:pressed { background: rgba(255, 255, 255, 14); }
QPushButton#copyCodeButton:focus { background: rgba(255, 255, 255, 8); }
QPlainTextEdit#codeEditor {
    color: #d9dce3;
    background: transparent;
    font-family: Consolas, "DejaVu Sans Mono", monospace;
    font-size: 14px;
    border: none;
    padding: 12px;
    selection-color: #ffffff;
    selection-background-color: #3e4551;
}
QPlainTextEdit#codeEditor QScrollBar:vertical,
QListWidget#skillPickerList QScrollBar:vertical { width: 11px; margin: 4px 1px; background: transparent; }
QPlainTextEdit#codeEditor QScrollBar:horizontal { height: 11px; margin: 1px 4px; background: transparent; }
QPlainTextEdit#codeEditor QScrollBar::handle:vertical,
QListWidget#skillPickerList QScrollBar::handle:vertical,
QPlainTextEdit#codeEditor QScrollBar::handle:horizontal { background: rgba(153, 161, 177, 90); border-radius: 4px; min-width: 28px; min-height: 28px; }
QPlainTextEdit#codeEditor QScrollBar::handle:hover,
QListWidget#skillPickerList QScrollBar::handle:hover { background: rgba(153, 161, 177, 140); }
QPlainTextEdit#codeEditor QScrollBar::add-line,
QListWidget#skillPickerList QScrollBar::add-line,
QListWidget#skillPickerList QScrollBar::sub-line,
QPlainTextEdit#codeEditor QScrollBar::sub-line { width: 0; height: 0; background: transparent; }
QPlainTextEdit#codeEditor QScrollBar::add-page,
QListWidget#skillPickerList QScrollBar::add-page,
QListWidget#skillPickerList QScrollBar::sub-page,
QPlainTextEdit#codeEditor QScrollBar::sub-page { background: transparent; }
QLabel#conversationStatus {
    color: #929292;
    background: transparent;
    min-height: 18px;
    padding: 0;
    font-size: 11px;
    font-family: Saira;
    font-weight: 400;
}
QWidget#messageComposer, QWidget#composerTools, QFrame#inlineApproval { background: transparent; border: none; }
QWidget#attachmentTray, QWidget#attachmentTray QWidget { background: transparent; }
QFrame#attachmentCard { background: rgba(19, 22, 30, 120); border: 1px solid rgba(145, 152, 171, 35); border-radius: 11px; }
QLabel#attachmentName { color: #d6d9e0; font-size: 12px; border: none; }
QLabel#attachmentDetail, QLabel#attachmentPreview { color: #a6aebe; font-size: 10px; border: none; }
QPushButton#attachmentRemove { color: #bec4d0; background: transparent; border: none; border-radius: 7px; font-size: 17px; padding: 0; }
QPushButton#attachmentRemove:hover { background: rgba(255, 255, 255, 15); color: #eeeeef; }
QLabel#attachmentHint { color: #b5bccb; font-size: 11px; background: transparent; padding-left: 20px; padding-right: 20px; }
QFrame#inlineApproval QLabel { background: transparent; border: none; font-size: 14px; }
QLabel#approvalTitle { color: #eeeeef; font-weight: 500; }
QLabel#approvalHint { color: #c6c9d2; }
QFrame#inlineApproval QPlainTextEdit {
    color: #e4e6eb; background: rgba(17, 19, 24, 100); border: none;
    border-radius: 6px; padding: 4px 6px; font-size: 14px;
    selection-background-color: #666666;
}
QPushButton#skillChip {
    color: #d5d6dc;
    background: rgba(18, 20, 26, 92);
    border: 1px solid rgba(200, 202, 210, 35);
    border-radius: 8px;
    padding: 2px 10px;
    font-family: Saira;
    font-size: 14px;
}
QPushButton#skillChip:hover { background: rgba(23, 25, 32, 128); }
QLabel#skillPickerEmpty { color: #b9bfcc; background: transparent; border: none; padding: 6px 8px; }
QListWidget#skillPickerList {
    color: #d9dce3; background: transparent; border: none; outline: none;
    font-family: Saira; font-size: 14px;
}
QListWidget#skillPickerList::item { padding: 6px 8px; border-radius: 6px; }
QListWidget#skillPickerList::item:selected { background: #3e4551; color: #ffffff; }
QListWidget#skillPickerList::item:hover:!selected { background: rgba(255, 255, 255, 8); }
QComboBox#modelSelector {
    color: #ededed;
    background: #262626;
    border: 1px solid #3c3c3c;
    border-radius: 12px;
    padding: 0 12px;
    font-family: Saira;
    font-size: 13px;
    font-weight: 400;
}
QComboBox#modelSelector:hover, QComboBox#modelSelector:focus { border-color: #666666; }
QComboBox#modelSelector::drop-down { border: none; width: 20px; }
QComboBox#modelSelector QAbstractItemView {
    color: #ededed;
    background: #262626;
    border: 1px solid #424242;
    selection-background-color: #3b3b3b;
}
QLineEdit#greetingInput {
    color: #ededed;
    background: #262626;
    border: 1px solid #3c3c3c;
    border-radius: 12px;
    padding: 0 12px;
    font-family: Saira;
    font-size: 13px;
    font-weight: 400;
    selection-background-color: #3b3b3b;
}
QLineEdit#greetingInput:hover, QLineEdit#greetingInput:focus { border-color: #666666; }
QScrollBar:vertical { background: transparent; width: 14px; margin: 0; }
QScrollBar::handle:vertical {
    background: #3f4149;
    border-radius: 6px;
    min-height: 72px;
    margin: 0 6px 0 0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
""" + COMPOSER_STYLE
