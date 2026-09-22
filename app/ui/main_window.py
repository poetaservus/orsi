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
    QPainterPath,
    QPalette,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.security.host_access import HostReadScope
from app.inference.engine import InferenceUnavailable
from app.ui.approvals import open_approval_dialog
from app.ui.chat import ChatView
from app.ui.context_window import ContextWindowBar
from app.ui.status import ConversationStatus
from app.ui.worker import ConversationWorker


log = logging.getLogger(__name__)


_ICON_DIRECTORY = Path(__file__).with_name("assets")
_FONT_DIRECTORY = _ICON_DIRECTORY / "fonts"
_TOP_BAR_HEIGHT = 68
_TOP_BAR_REVEAL_HEIGHT = 6
_TOP_BAR_ANIMATION_MS = 220
_TOP_BAR_HIDE_DELAY_MS = 450
_TOP_BUTTON_SIZE = 42
_TOP_ICON_SIZE = 30
_COMPOSER_WIDTH = 799
_COMPOSER_HEIGHT = 54
_COMPOSER_BOTTOM_MARGIN = 42
_DEFAULT_GREETING_TEXT = "Lets Roll."
_GREETING_MAX_LENGTH = 80
_STARTUP_GREETING_HEIGHT = 64
_STARTUP_GREETING_GAP = 24
_STARTUP_TRANSITION_MS = 340
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


class MessageInput(QTextEdit):
    submit_requested = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        is_return = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ComposerFrame(QFrame):
    """Paint a clean v2 composer pill without baked-in image artifacts."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor("#41444d"))
        fill.setColorAt(0.45, QColor("#383b45"))
        fill.setColorAt(1.0, QColor("#303340"))
        painter.setPen(QColor(105, 109, 124, 190))
        painter.setBrush(fill)
        painter.drawPath(path)

        painter.setPen(QColor(255, 255, 255, 26))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inner = rect.adjusted(2.0, 2.0, -2.0, -2.0)
        painter.drawRoundedRect(inner, max(1.0, radius - 2.0), max(1.0, radius - 2.0))


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
        self.inference = inference
        self.startup_error = startup_error
        self._preferences_store = preferences_store
        self._greeting_message = self._load_greeting_message()
        self._cloud_privacy_accepted = False
        self.thread = None
        self.worker = None
        self._approval_dialog = None
        self.approval_requested.connect(self._show_approval, Qt.ConnectionType.QueuedConnection)
        bind_approval = getattr(service, "set_approval_requester", None)
        if callable(bind_approval):
            bind_approval(self.approval_requested.emit)

        self.setObjectName("mainWindow")
        self.setWindowTitle("O.R.S.I")
        self.resize(1280, 800)
        self.setMinimumSize(760, 600)

        root = QWidget()
        self._root = root
        root.setObjectName("root")
        root.installEventFilter(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        topbar = QWidget(root)
        self.topbar = topbar
        topbar.setObjectName("topBar")
        topbar.setFixedHeight(_TOP_BAR_HEIGHT)
        topbar.installEventFilter(self)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(21, 0, 22, 0)
        topbar_layout.setSpacing(17)

        self.new_session_button = QPushButton()
        self.new_session_button.setObjectName("topBarButton")
        self.new_session_button.setFixedSize(_TOP_BUTTON_SIZE, _TOP_BUTTON_SIZE)
        self.new_session_button.setIcon(QIcon(str(_ICON_DIRECTORY / "new_message_icon_cropped.png")))
        self.new_session_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.new_session_button.setToolTip("New session — permanently clears this conversation")
        self.new_session_button.setAccessibleName("New session")
        self.new_session_button.setEnabled(service is not None)

        first_separator = QFrame()
        first_separator.setObjectName("topBarSeparator")
        first_separator.setFixedSize(1, 28)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("topBarButton")
        self.settings_button.setFixedSize(_TOP_BUTTON_SIZE, _TOP_BUTTON_SIZE)
        self.settings_button.setIcon(QIcon(str(_ICON_DIRECTORY / "settings_icon_cropped.png")))
        self.settings_button.setIconSize(QSize(_TOP_ICON_SIZE, _TOP_ICON_SIZE))
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")

        topbar_layout.addWidget(self.new_session_button, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addWidget(first_separator, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignVCenter)
        topbar_layout.addStretch(1)
        self.context_window = ContextWindowBar(
            int(getattr(inference, "context_length", 0)),
            topbar,
        )
        topbar_layout.addWidget(self.context_window, 0, Qt.AlignmentFlag.AlignVCenter)

        self._topbar_expanded = False
        self._topbar_animation = QPropertyAnimation(topbar, b"pos", self)
        self._topbar_hide_timer = QTimer(self)
        self._topbar_hide_timer.setSingleShot(True)
        self._topbar_hide_timer.timeout.connect(self._hide_topbar_if_idle)

        content = ChatSurface()
        self._content = content
        content.installEventFilter(self)
        content_layout = QVBoxLayout(content)
        self._content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        self.chat = ChatView()
        content_layout.addWidget(self.chat, 1)

        self.settings_panel = QFrame(root)
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setFixedSize(314, 226)
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(18, 16, 18, 16)
        settings_layout.setSpacing(8)

        settings_title = QLabel("Settings")
        settings_title.setObjectName("settingsTitle")
        settings_layout.addWidget(settings_title)

        model_label = QLabel("Model")
        model_label.setObjectName("settingsLabel")
        settings_layout.addWidget(model_label)

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
        settings_layout.addWidget(self.model_selector)

        greeting_label = QLabel("Greeting")
        greeting_label.setObjectName("settingsLabel")
        settings_layout.addWidget(greeting_label)

        self.greeting_input = QLineEdit()
        self.greeting_input.setObjectName("greetingInput")
        self.greeting_input.setFixedHeight(38)
        self.greeting_input.setMaxLength(_GREETING_MAX_LENGTH)
        self.greeting_input.setText(self._greeting_message)
        settings_layout.addWidget(self.greeting_input)

        self.activity = ConversationStatus(
            self._ready_status() if not startup_error else "Model unavailable"
        )
        settings_layout.addWidget(self.activity)
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
        composer_layout = QHBoxLayout(self.composer)
        composer_layout.setContentsMargins(22, 7, 20, 7)
        composer_layout.setSpacing(6)

        self.input = MessageInput()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Ask O.R.S.I.")
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(41)
        self.input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        input_palette = self.input.palette()
        input_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#a2a8ba"))
        self.input.setPalette(input_palette)

        self.action_slot = QWidget()
        self.action_slot.setObjectName("composerActionSlot")
        self.action_slot.setFixedSize(34, 37)

        self.send = QPushButton(self.action_slot)
        self.send.setObjectName("sendButton")
        self.send.setFixedSize(34, 34)
        self.send.move(0, 4)
        self.send.setIcon(QIcon(str(_ICON_DIRECTORY / "input_button_cropped.png")))
        self.send.setIconSize(QSize(27, 27))
        self.send.setToolTip("Send")
        self.send.setAccessibleName("Send")

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

        composer_layout.addWidget(self.input, 1)
        composer_layout.addWidget(self.action_slot)

        self.setCentralWidget(root)
        self.setStyleSheet(_STYLE)
        _apply_ui_font(self.input)
        self.send.clicked.connect(self.submit)
        self.stop.clicked.connect(self.cancel_current_task)
        self.new_session_button.clicked.connect(self.create_new_session)
        self.settings_button.clicked.connect(self._toggle_settings)
        self.input.submit_requested.connect(self.submit)
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
        self._update_context_window()
        self._position_overlays()
        if startup_error:
            self.chat.add_message("Agent", startup_error, True)
        elif self._agent_error():
            self.chat.add_message("Agent", self._agent_error(), True)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._position_overlays()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if hasattr(self, "_greeting_save_timer") and self._greeting_save_timer.isActive():
            self._greeting_save_timer.stop()
            self._save_greeting_message()
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name
        if watched is getattr(self, "topbar", None):
            if event.type() == QEvent.Type.Enter:
                self._topbar_hide_timer.stop()
                self._set_topbar_expanded(True)
            elif event.type() == QEvent.Type.Leave:
                self._schedule_topbar_hide()
        if watched in {
            getattr(self, "_root", None),
            getattr(self, "_content", None),
        } and event.type() == QEvent.Type.Resize:
            self._position_overlays()
        return super().eventFilter(watched, event)

    def _schedule_topbar_hide(self) -> None:
        if self.settings_panel.isVisible():
            return
        self._topbar_hide_timer.start(_TOP_BAR_HIDE_DELAY_MS)

    def _hide_topbar_if_idle(self) -> None:
        if self.settings_panel.isVisible() or self.topbar.underMouse():
            return
        self._set_topbar_expanded(False)

    def _set_topbar_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        if expanded:
            self._topbar_hide_timer.stop()
        elif self.settings_panel.isVisible():
            return
        self._topbar_expanded = expanded
        target = QPoint(
            0,
            0 if expanded else -(_TOP_BAR_HEIGHT - _TOP_BAR_REVEAL_HEIGHT),
        )
        self._topbar_animation.stop()
        if not animate or not self.isVisible():
            self.topbar.move(target)
            return
        self._topbar_animation.setDuration(_TOP_BAR_ANIMATION_MS)
        self._topbar_animation.setStartValue(self.topbar.pos())
        self._topbar_animation.setEndValue(target)
        self._topbar_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic if expanded else QEasingCurve.Type.InCubic
        )
        self._topbar_animation.start()

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
        self.topbar.resize(self._root.width(), _TOP_BAR_HEIGHT)
        if self._topbar_animation.state() != QPropertyAnimation.State.Running:
            self.topbar.move(
                0,
                0
                if self._topbar_expanded
                else -(_TOP_BAR_HEIGHT - _TOP_BAR_REVEAL_HEIGHT),
            )
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
        self.topbar.raise_()
        self.settings_panel.move(92, _TOP_BAR_HEIGHT + 12)
        if self.settings_panel.isVisible():
            self.settings_panel.raise_()

    def _composer_target_geometry(self) -> QRect:
        content = self.composer.parentWidget()
        width = min(_COMPOSER_WIDTH, max(320, content.width() - 32))
        x = max(16, (content.width() - width) // 2)
        if self._intro_active:
            y = max(24, (content.height() - _COMPOSER_HEIGHT) // 2)
        else:
            y = max(16, content.height() - _COMPOSER_BOTTOM_MARGIN - _COMPOSER_HEIGHT)
        return QRect(x, y, width, _COMPOSER_HEIGHT)

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
            self._set_topbar_expanded(True)
            self.settings_panel.raise_()
        else:
            self._schedule_topbar_hide()

    def submit(self) -> None:
        message = self.input.toPlainText().strip()
        if not message or self.thread is not None:
            return
        if self.startup_error:
            self.chat.add_message("Agent", self.startup_error, True)
            return
        if self.inference is not None and self.inference.mode == "cloud" and not self._ensure_cloud_ready():
            return

        self.input.clear()
        self._leave_intro_mode()
        self.chat.add_message("User", message)
        self._set_busy(True)
        self.thread = QThread()
        self.worker = ConversationWorker(self.service, message)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._worker_succeeded)
        self.worker.failed.connect(self._worker_failed)
        self.worker.activity.connect(self.activity.set_activity)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot(object)
    def _show_approval(self, record) -> None:
        if self._approval_dialog is not None:
            self.service.resolve_approval(record.approval_id, False)
            return
        opened = open_approval_dialog(
            self,
            self.service,
            record,
            self._approval_finished,
        )
        if opened is None:
            return
        self._approval_dialog, activity = opened
        self.activity.set_activity(activity)

    def _approval_finished(self) -> None:
        self._approval_dialog = None

    @Slot(str)
    def _worker_succeeded(self, text: str) -> None:
        self._done(text, False)

    @Slot(str)
    def _worker_failed(self, text: str) -> None:
        self._done(text, True)

    def _done(self, text: str, error: bool) -> None:
        if self.inference is not None:
            notice = self.inference.consume_notice()
            if notice:
                text = f"{text}\n\n{notice}"
            self._sync_inference_selector()
        self._update_context_window()
        duration_seconds = self._set_busy(False)
        self.chat.add_message(
            "Agent",
            text,
            error,
            duration_seconds=duration_seconds,
        )

    @Slot()
    def _thread_finished(self) -> None:
        self.thread.deleteLater()
        self.thread = None
        self.worker = None

    def _set_busy(self, busy: bool) -> float | None:
        self.send.setEnabled(not busy)
        self.stop.setEnabled(busy and self.service is not None)
        self.send.setVisible(not busy)
        self.stop.setVisible(busy)
        self.input.setEnabled(not busy)
        self.model_selector.setEnabled(not busy and self.inference is not None)
        self.new_session_button.setEnabled(not busy and self.service is not None)
        duration_seconds = self.chat.set_thinking(busy)
        self.activity.set_activity("" if busy else self._ready_status())
        return duration_seconds

    def cancel_current_task(self) -> None:
        cancel = getattr(self.service, "cancel_current_task", None)
        if callable(cancel):
            cancel()
            self.stop.setEnabled(False)
            self.activity.set_activity("Stopping...")

    def create_new_session(self) -> None:
        if self.thread is not None:
            return
        reset = getattr(self.service, "new_session", None)
        if not callable(reset):
            return
        try:
            reset()
        except Exception as exc:
            self.chat.add_message("Agent", str(exc), True)
            return
        self.chat.clear_messages()
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
            if "filesystem.mkdir" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Folder approval"
            if "filesystem.write_text" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Text-write approval"
            if "filesystem.copy" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Copy approval"
            if "filesystem.move" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Move approval"
            if "filesystem.trash" in getattr(self.service, "agent_capabilities", ()):
                read_status += " · Trash approval"
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
        if self.inference is None or index < 0:
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
        self._update_context_window()
        self.activity.set_activity(self._ready_status())

    def _ensure_cloud_ready(self) -> bool:
        if self.inference is None:
            return False
        if not self._cloud_privacy_accepted:
            answer = QMessageBox.question(
                self,
                "Use cloud model?",
                self._cloud_privacy_message(),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            self._cloud_privacy_accepted = True
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

    def _cloud_privacy_message(self) -> str:
        provider = self.inference.cloud_provider_name
        if self._agent_enabled():
            scope = (
                "across enabled local filesystem drives that the current Windows account can access"
                if self._host_read_scope() == HostReadScope.FULL_LOCAL
                else "inside O.R.S.I's portable root"
            )
            find_enabled = self._filesystem_find_enabled()
            listing_enabled = self._filesystem_list_enabled()
            text_read_enabled = self._filesystem_read_text_enabled()
            search_enabled = self._filesystem_search_enabled()
            result_parts = ["filesystem.stat metadata"]
            access_parts = ["inspect metadata"]
            if find_enabled:
                result_parts.append("filesystem.find matching file and folder names")
                access_parts.append("resolve exact file or folder names inside one requested folder")
            if listing_enabled:
                result_parts.append("filesystem.list directory names and types")
                access_parts.append("list one requested directory")
            if text_read_enabled:
                result_parts.append("filesystem.read_text file content")
                access_parts.append("read bounded text from one specifically requested file")
            if search_enabled:
                result_parts.append("filesystem.search matching snippets")
                access_parts.append("search bounded text snippets inside one requested directory")
            if len(result_parts) == 1:
                results = f"{result_parts[0]} results"
            elif len(result_parts) == 2:
                results = " and ".join(result_parts)
            else:
                results = ", ".join(result_parts[:-1]) + f", and {result_parts[-1]}"
            if len(access_parts) == 1:
                access = f"{access_parts[0]} for one requested file or directory"
            elif len(access_parts) == 2:
                access = " or ".join(access_parts)
            else:
                access = ", ".join(access_parts[:-1]) + f", or {access_parts[-1]}"
            if text_read_enabled or search_enabled:
                boundary = "but cannot write or perform other computer actions"
                confidentiality = (
                    "File content, snippets, and directory or file names may be confidential"
                    if search_enabled
                    else "File content and directory or file names may be confidential"
                )
            else:
                boundary = "but cannot read file content, search, or perform other computer actions"
                confidentiality = "Directory and file names may be confidential"
            mkdir_enabled = "filesystem.mkdir" in getattr(self.service, "agent_capabilities", ())
            text_write_enabled = "filesystem.write_text" in getattr(self.service, "agent_capabilities", ())
            copy_enabled = "filesystem.copy" in getattr(self.service, "agent_capabilities", ())
            move_enabled = "filesystem.move" in getattr(self.service, "agent_capabilities", ())
            trash_enabled = "filesystem.trash" in getattr(self.service, "agent_capabilities", ())
            write_actions = []
            approved_results = []
            if mkdir_enabled:
                write_actions.append("create one empty folder")
                approved_results.append("approved folder paths")
            if text_write_enabled:
                write_actions.append("create or replace one text file")
                approved_results.append("text-write paths and content")
            if copy_enabled:
                write_actions.append("copy one regular file")
                approved_results.append("copy paths")
            if move_enabled:
                write_actions.append("move one regular file")
                approved_results.append("move paths")
            if trash_enabled:
                write_actions.append("send one regular file to the Recycle Bin")
                approved_results.append("trash paths")
            if write_actions:
                if len(write_actions) == 1:
                    actions = write_actions[0]
                else:
                    actions = ", ".join(write_actions[:-1]) + f", or {write_actions[-1]}"
                delete_boundary = (
                    "it cannot permanently delete entries or trash directories"
                    if trash_enabled
                    else "it cannot trash entries or delete anything except the source of an approved move"
                    if move_enabled
                    else "it cannot move, trash, or delete entries"
                )
                boundary = (
                    f"and can {actions} only after separate approval of exact paths and, when "
                    f"relevant, exact content or collision policy; {delete_boundary}"
                )
                if len(approved_results) == 1:
                    results += f" plus {approved_results[0]}"
                else:
                    results += " plus " + ", ".join(approved_results[:-1]) + f", and {approved_results[-1]}"
            return (
                f"Cloud mode sends this conversation and any {results} to {provider}. Agent mode "
                f"can {access} {scope}, {boundary}.\n\n{confidentiality}. Do not use Cloud mode "
                "for confidential information.\n\nContinue?"
            )
        return (
            f"Cloud mode sends this conversation to {provider}. O.R.S.I is chat-only and cannot "
            "access or operate your computer.\n\nDo not use Cloud mode for confidential "
            "information.\n\nContinue?"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._approval_dialog is not None:
            self._approval_dialog.reject()
        shutdown = getattr(self.service, "shutdown", None)
        if callable(shutdown):
            shutdown()
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
QWidget#topBar {
    background: #050506;
    border-bottom: 1px solid #101217;
}
QPushButton#topBarButton {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 0;
}
QPushButton#topBarButton:hover { background: #15161a; }
QPushButton#topBarButton:pressed { background: #202128; }
QPushButton#topBarButton:disabled { background: transparent; }
QFrame#topBarSeparator {
    background: #15161a;
    border: none;
}
QFrame#settingsPanel {
    background: #252627;
    border: 1px solid #3a3b3c;
    border-radius: 15px;
}
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
    border-radius: 27px;
}
QFrame#orsiMessage, QFrame#errorMessage { background: transparent; border: none; }
QFrame#userMessage QLabel, QFrame#orsiMessage QLabel {
    color: #e3e3e4;
    font-family: Saira;
    font-size: 18px;
    font-weight: 400;
}
QFrame#userMessage QLabel { font-size: 18px; }
QFrame#errorMessage QLabel {
    color: #ff8d86;
    font-family: Saira;
    font-size: 15px;
    font-weight: 400;
}
QWidget#messageMetaRow, QWidget#messageActionRow {
    background: transparent;
    border: none;
}
QLabel#responseTiming {
    color: #858791;
    background: transparent;
    border: none;
    font-family: Saira;
    font-size: 11px;
    font-weight: 400;
}
QPushButton#copyMessageButton {
    color: #b7b8bd;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0 7px;
    font-family: Saira;
    font-size: 11px;
    font-weight: 400;
}
QPushButton#copyMessageButton:hover { color: #ededee; background: #292a30; }
QPushButton#copyMessageButton:pressed { background: #1e1f24; }
QFrame#codeBlock {
    background: #202020;
    border: 1px solid #3b3b3b;
    border-radius: 9px;
}
QWidget#codeHeader {
    background: #292929;
    border: none;
    border-bottom: 1px solid #3b3b3b;
}
QLabel#codeLanguage {
    color: #a9a9a9;
    background: transparent;
    border: none;
    font-size: 11px;
    font-family: Saira;
    font-weight: 400;
}
QPushButton#copyCodeButton {
    color: #d8d8d8;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0 7px;
    font-size: 11px;
    font-family: Saira;
    font-weight: 400;
}
QPushButton#copyCodeButton:hover { background: #383838; }
QPushButton#copyCodeButton:pressed { background: #222222; }
QPlainTextEdit#codeEditor {
    color: #e8e8e8;
    background: #202020;
    border: none;
    padding: 9px;
    selection-color: #ffffff;
    selection-background-color: #505050;
}
QLabel#conversationStatus {
    color: #929292;
    background: transparent;
    min-height: 18px;
    padding: 0;
    font-size: 11px;
    font-family: Saira;
    font-weight: 400;
}
QFrame#composer {
    background: transparent;
    border: none;
    border-radius: 27px;
}
QTextEdit#messageInput {
    color: #dedee0;
    background: transparent;
    border: none;
    padding: 4px 0 3px 4px;
    font-family: Saira;
    font-size: 17px;
    font-weight: 400;
    selection-background-color: #666666;
}
QTextEdit#messageInput:focus { border: none; }
QTextEdit#messageInput:disabled { color: #777777; background: transparent; }
QPushButton#sendButton, QPushButton#stopButton {
    background: transparent;
    border: none;
    border-radius: 17px;
    padding: 0;
}
QPushButton#sendButton:hover, QPushButton#stopButton:hover { background: #454852; }
QPushButton#sendButton:pressed, QPushButton#stopButton:pressed { background: #2c2e35;  }
QPushButton#sendButton:disabled, QPushButton#stopButton:disabled { background: transparent; }
QComboBox#modelSelector {
    color: #ededed;
    background: #262626;
    border: 1px solid #3c3c3c;
    border-radius: 12px;
    padding: 0 12px;
    min-width: 92px;
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
"""
