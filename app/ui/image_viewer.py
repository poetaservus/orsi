"""Large image inspection over the blurred chat with its shared composer."""
from PySide6.QtCore import QLineF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene,
    QFileDialog, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.inference.attachments import attachment_references
from app.ui.composer import (
    ASSETS, COMPOSER_HEIGHT, COMPOSER_WIDTH, COMPOSER_STYLE, ComposerFrame,
    MessageInput, composer_tools, configure_input, configure_send,
)
from app.ui.message_images import MessageImageLoader


def _blurred_backdrop(parent):
    # Capture only O.R.S.I's own widget, once before opening the overlay.
    # Never capture the desktop or blur the foreground image and composer.
    source = parent.grab() if parent is not None else QPixmap(str(ASSETS / "o.r.s.i_gui_bck.png"))
    if source.isNull():
        return source
    source = source.scaled(QSize(1280, 900), Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    source.setDevicePixelRatio(1.)
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(source.rect()))
    item = QGraphicsPixmapItem(source)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(28.)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    result = QPixmap(source.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(result.rect()), QRectF(source.rect()))
    painter.end()
    return result


class _NavigationButton(QPushButton):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.setObjectName("imageViewerNavigation")
        self.setFixedSize(36, 36)
        self.setAutoDefault(False)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#cbd0da" if self.isEnabled() else "#545964"), 1.3,
            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.translate(self.width() / 2, self.height() / 2)
        if self.action == 'close':
            painter.drawLine(QLineF(-4, -4, 4, 4))
            painter.drawLine(QLineF(4, -4, -4, 4))
        else:
            direction = -1 if self.action == 'previous' else 1
            painter.drawLine(QLineF(-3 * direction, -5, 3 * direction, 0))
            painter.drawLine(QLineF(3 * direction, 0, -3 * direction, 5))


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

    def target_rect(self, image):
        bounds = self.rect().adjusted(8, 4, -8, -4)
        size = image.size().scaled(bounds.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(bounds.center().x() - size.width() / 2,
                      bounds.center().y() - size.height() / 2, size.width(), size.height())

    def paintEvent(self, event):  # noqa: N802
        if self.reference is None:
            return
        image = self.loader.image(self.reference)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if image is None or image.isNull():
            painter.setPen(QColor("#b1b8c8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Opening image…" if image is None else "This saved image is unavailable.")
            return
        target = self.target_rect(image)
        path = QPainterPath()
        path.addRoundedRect(target, 6, 6)
        painter.setClipPath(path)
        painter.drawImage(target, image)


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._backdrop = _blurred_backdrop(parent)
        self.loader = MessageImageLoader(store, self, size=QSize(4096, 4096), max_cached=2)
        self.loader.loaded.connect(self._refresh_send)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 28)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.name = QLabel()
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.counter = QLabel()
        self.counter.setObjectName("imageViewerCounter")
        self.previous = _NavigationButton('previous')
        self.previous.setAccessibleName("Previous image")
        self.next = _NavigationButton('next')
        self.next.setAccessibleName("Next image")
        self.close_button = _NavigationButton('close')
        self.save_button = QPushButton("Save image…")
        self.save_button.setObjectName("imageViewerSave")
        self.save_button.setAccessibleName("Save original image")
        self.save_button.clicked.connect(self._save_image)
        self.close_button.setAccessibleName("Close image viewer")
        header.addWidget(self.name, 1)
        header.addWidget(self.counter)
        header.addWidget(self.save_button)
        header.addWidget(self.previous)
        header.addWidget(self.next)
        header.addSpacing(8)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.canvas = _ImageCanvas(self.loader)
        layout.addWidget(self.canvas, 1)

        self.include_all = QCheckBox(f"Include all {len(self.references)} images")
        self.include_all.setVisible(len(self.references) > 1)
        self.include_all.setEnabled(cloud)
        if not cloud:
            self.include_all.setToolTip("Local mode sends the image you are viewing, one per message.")
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setObjectName("imageViewerStatus")
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(self.include_all)
        footer.addWidget(self.status)
        footer.addStretch()
        layout.addLayout(footer)

        self.composer = ComposerFrame(self)
        self.composer.setObjectName("composer")
        self.composer.setFixedHeight(COMPOSER_HEIGHT)
        self.composer.setMaximumWidth(COMPOSER_WIDTH)
        self.composer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        composer = QHBoxLayout(self.composer)
        composer.setContentsMargins(22, 7, 20, 7)
        composer.setSpacing(6)
        self.tools, self.add_placeholder, self.folder_placeholder = composer_tools(self.composer)
        self.add_placeholder.setAccessibleName("Choose images to include")
        self.add_placeholder.setToolTip("Choose images to include")
        self.prompt = MessageInput()
        configure_input(self.prompt)
        self.prompt.setAccessibleName("New prompt with this image")
        self.action_slot = QWidget()
        self.action_slot.setFixedSize(34, 37)
        self.send = QPushButton(self.action_slot)
        configure_send(self.send)
        self.send.move(0, 4)
        self.send.setAccessibleName("Send prompt with image")
        self.send.setToolTip("Send with image · Enter (Shift+Enter for a new line)")
        composer.addWidget(self.tools, 0, Qt.AlignmentFlag.AlignVCenter)
        composer.addWidget(self.prompt, 1)
        composer.addWidget(self.action_slot)
        composer_row = QHBoxLayout()
        composer_row.addStretch(1)
        composer_row.addWidget(self.composer, 10)
        composer_row.addStretch(1)
        layout.addLayout(composer_row)
        self.add_placeholder.clicked.connect(self._choose_images)
        self.previous.clicked.connect(lambda: self.navigate(-1))
        self.next.clicked.connect(lambda: self.navigate(1))
        self.close_button.clicked.connect(self.reject)
        self.prompt.textChanged.connect(self._refresh_send)
        self.prompt.submit_requested.connect(self._submit)
        self.prompt.attachments_requested.connect(lambda _: self.status.setText("Use the chat composer to attach additional files."))
        self.send.clicked.connect(self._submit)
        self.finished.connect(self._clear)
        self.setStyleSheet(_STYLE + COMPOSER_STYLE)
        self.setGeometry(self.screen().availableGeometry())
        self._refresh_image()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#080a0f"))
        if not self._backdrop.isNull():
            source = QRectF(self._backdrop.rect())
            scale = max(self.width() / source.width(), self.height() / source.height())
            width, height = source.width() * scale, source.height() * scale
            painter.drawPixmap(QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height), self._backdrop, source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 182))

    def _clear(self, *_):
        self.loader.clear()
        self._backdrop = QPixmap()

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

    def _choose_images(self):
        menu = QMenu(self)
        current = menu.addAction("This image")
        current.setCheckable(True)
        current.setChecked(not self.include_all.isChecked())
        current.triggered.connect(lambda: self.include_all.setChecked(False))
        if len(self.references) > 1:
            all_images = menu.addAction(f"All {len(self.references)} images")
            all_images.setCheckable(True)
            all_images.setChecked(self.include_all.isChecked())
            all_images.setEnabled(self.include_all.isEnabled())
            all_images.triggered.connect(lambda: self.include_all.setChecked(True))
        menu.popup(self.add_placeholder.mapToGlobal(self.add_placeholder.rect().topLeft()))
        menu.aboutToHide.connect(menu.deleteLater)

    def _save_image(self):
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(self, "Save original image", self.reference.name,
                                             "Images (*.png *.jpg *.jpeg *.webp);;All files (*)")
        if not path:
            return
        try:
            self._export_original(Path(path))
        except Exception:
            self.status.setText("Could not save the image. Choose another location and try again.")
            return
        self.status.setText("Image saved.")

    def _export_original(self, path):
        # QSaveFile preserves the original encoded bytes and commits atomically.
        from PySide6.QtCore import QSaveFile, QIODevice
        target = QSaveFile(str(path))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError("Image destination is unavailable.")
        try:
            with self.loader.store.open(self.reference) as source:
                while chunk := source.read(1024 * 1024):
                    if target.write(chunk) != len(chunk):
                        raise OSError("Image save failed.")
            if not target.commit():
                raise OSError("Image save failed.")
        finally:
            if target.isOpen():
                target.cancelWriting()

    def set_reply_available(self, available):
        self._available = available
        self.status.setText("" if available else "Wait for the current reply to finish.")
        self._refresh_send()

    def set_preparing(self):
        self._preparing = True
        self.prompt.setEnabled(False)
        self.include_all.setEnabled(False)
        self.add_placeholder.setEnabled(False)
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
QDialog#imageViewer { color: #dce2ee; font-family: Saira; background: transparent; border: none; }
QWidget { background: transparent; }
QLabel { color: #dce2ee; font-size: 13px; }
QLabel#imageViewerCounter, QLabel#imageViewerStatus { color: #939cac; font-size: 12px; }
QPushButton#imageViewerNavigation { background: rgba(28, 30, 35, 180); border: none; border-radius: 18px; padding: 0; }
QPushButton#imageViewerNavigation:hover { background: #353840; }
QPushButton#imageViewerSave { color: #cad3e2; background: rgba(28, 30, 35, 180); border: 1px solid #414550; border-radius: 8px; padding: 5px 10px; }
QPushButton#imageViewerSave:hover { background: #353840; }
QDialog#imageViewer QCheckBox { color: #b1b8c8; font-size: 12px; }
QMenu { color: #dce2ee; background: #252830; border: 1px solid #414550; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 16px; border-radius: 4px; }
QMenu::item:selected { background: #3e424d; }
QMenu::item:disabled { color: #747b8a; }
"""
