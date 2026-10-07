"""Near-screen-size image inspection with an explicit image follow-up composer."""
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.inference.attachments import attachment_references
from app.ui.message_images import MessageImageLoader


class _ImageCanvas(QWidget):
    def __init__(self, loader):
        super().__init__()
        self.loader, self.reference = loader, None
        self.setObjectName("imageViewerCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        loader.loaded.connect(self._loaded)

    def _loaded(self, key):
        if self.reference is not None and key == self.reference.id:
            self.update()

    def paintEvent(self, event):  # noqa: N802
        if self.reference is None:
            return
        image = self.loader.image(self.reference)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = self.rect().adjusted(16, 12, -16, -12)
        if image is None or image.isNull():
            painter.setPen(QColor("#b1b8c8"))
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter,
                             "Opening image…" if image is None else "This saved image is unavailable.")
            return
        size = image.size().scaled(bounds.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(bounds.center().x() - size.width() / 2,
                        bounds.center().y() - size.height() / 2, size.width(), size.height())
        painter.drawImage(target, image)


class _ImagePrompt(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ImageViewer(QDialog):
    reply_requested = Signal(object, str)

    def __init__(self, store, references, index=0, *, cloud=False, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.references = attachment_references(references)
        if not self.references or any(ref.kind != "image" for ref in self.references):
            raise ValueError("The viewer requires saved image references.")
        self.index = min(max(0, index), len(self.references) - 1)
        self._available, self._preparing = True, False
        self.setObjectName("imageViewer")
        self.setWindowTitle("Image · O.R.S.I.")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.loader = MessageImageLoader(store, self, size=QSize(3840, 2160), max_cached=2)
        self.loader.loaded.connect(self._refresh_send)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.name = QLabel()
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.counter = QLabel()
        self.counter.setObjectName("imageViewerCounter")
        self.previous = QPushButton("‹")
        self.previous.setAccessibleName("Previous image")
        self.next = QPushButton("›")
        self.next.setAccessibleName("Next image")
        self.close_button = QPushButton("×")
        self.close_button.setAccessibleName("Close image viewer")
        for button in (self.previous, self.next, self.close_button):
            button.setFixedSize(36, 32)
            button.setAutoDefault(False)
        header.addWidget(self.name, 1)
        header.addWidget(self.counter)
        header.addWidget(self.previous)
        header.addWidget(self.next)
        header.addSpacing(8)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.canvas = _ImageCanvas(self.loader)
        layout.addWidget(self.canvas, 1)
        separator = QFrame()
        separator.setObjectName("imageViewerSeparator")
        separator.setFixedHeight(1)
        layout.addWidget(separator)
        footer = QHBoxLayout()
        self.include_all = QCheckBox(f"Include all {len(self.references)} images")
        self.include_all.setVisible(len(self.references) > 1)
        self.include_all.setEnabled(cloud)
        if not cloud:
            self.include_all.setToolTip("Local mode sends the image you are viewing, one per message.")
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setObjectName("imageViewerStatus")
        footer.addWidget(self.include_all)
        footer.addWidget(self.status, 1)
        layout.addLayout(footer)
        composer = QHBoxLayout()
        self.prompt = _ImagePrompt()
        self.prompt.setObjectName("imageViewerPrompt")
        self.prompt.setPlaceholderText("Ask about this image…")
        self.prompt.setAccessibleName("New prompt with this image")
        self.prompt.setFixedHeight(72)
        self.send = QPushButton()
        self.send.setObjectName("imageViewerSend")
        self.send.setIcon(QIcon(str(Path(__file__).with_name("assets") / "input_button_cropped.png")))
        self.send.setIconSize(QSize(27, 27))
        self.send.setFixedSize(44, 44)
        self.send.setAutoDefault(False)
        self.send.setAccessibleName("Send prompt with image")
        self.send.setToolTip("Send with image · Enter (Shift+Enter for a new line)")
        composer.addWidget(self.prompt, 1)
        composer.addWidget(self.send)
        layout.addLayout(composer)
        self.previous.clicked.connect(lambda: self.navigate(-1))
        self.next.clicked.connect(lambda: self.navigate(1))
        self.close_button.clicked.connect(self.reject)
        self.prompt.textChanged.connect(self._refresh_send)
        self.prompt.submitted.connect(self._submit)
        self.send.clicked.connect(self._submit)
        self.finished.connect(lambda: self.loader.clear())
        self.setStyleSheet(_STYLE)
        self._refresh_image()
        screen = self.screen().availableGeometry()
        self.resize(round(screen.width() * .94), round(screen.height() * .92))
        self.move(screen.center() - self.rect().center())

    @property
    def reference(self):
        return self.references[self.index]

    def navigate(self, delta):
        self.index = min(max(0, self.index + delta), len(self.references) - 1)
        self._refresh_image()

    def _refresh_image(self):
        self.name.setText(self.reference.name)
        self.name.setToolTip(self.reference.name)
        self.counter.setText(f"{self.index + 1} / {len(self.references)}")
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(self.index < len(self.references) - 1)
        self.canvas.reference = self.reference
        self.canvas.update()
        self._refresh_send()

    def set_reply_available(self, available):
        self._available = available
        self.status.setText("" if available else "Wait for the current reply to finish.")
        self._refresh_send()

    def set_preparing(self):
        self._preparing = True
        self.prompt.setEnabled(False)
        self.include_all.setEnabled(False)
        self.status.setText("Preparing your image…")
        self._refresh_send()

    def _refresh_send(self, *_):
        image = self.loader._images.get(self.reference.id)
        self.send.setEnabled(self._available and not self._preparing and bool(self.prompt.toPlainText().strip())
                             and image is not None and not image.isNull())

    def _submit(self):
        self._refresh_send()
        if self.send.isEnabled():
            refs = self.references if self.include_all.isChecked() else (self.reference,)
            self.reply_requested.emit(refs, self.prompt.toPlainText())

    def keyPressEvent(self, event):  # noqa: N802
        if not self.prompt.hasFocus() and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.navigate(-1 if event.key() == Qt.Key.Key_Left else 1)
            event.accept()
        else:
            super().keyPressEvent(event)


_STYLE = """
QDialog#imageViewer { background: #12151d; border: 1px solid #39404e; border-radius: 14px; }
QDialog#imageViewer QWidget { color: #dce2ee; font-family: Saira; background: transparent; }
QDialog#imageViewer QLabel { font-size: 14px; }
QDialog#imageViewer QLabel#imageViewerCounter, QDialog#imageViewer QLabel#imageViewerStatus { color: #939cac; font-size: 12px; }
QDialog#imageViewer QFrame#imageViewerSeparator { background: #303744; }
QDialog#imageViewer QPushButton { border: none; border-radius: 8px; font-size: 25px; padding: 0; }
QDialog#imageViewer QPushButton:hover { background: #2c3340; }
QDialog#imageViewer QPushButton:disabled { color: #50596a; }
QDialog#imageViewer QPlainTextEdit#imageViewerPrompt { background: #242b38; border: 1px solid #414958; border-radius: 14px; padding: 10px 14px; font-size: 16px; selection-background-color: #485264; }
QDialog#imageViewer QPushButton#imageViewerSend { background: #2b3341; border: 1px solid #4a5262; border-radius: 22px; }
QDialog#imageViewer QCheckBox { color: #b1b8c8; font-size: 12px; }
"""
