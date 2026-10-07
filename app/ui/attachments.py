"""Ordered composer drafts and off-thread attachment preparation."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.conversation.attachment_processing import AttachmentProcessor, MAX_IMAGE_PIXELS
from app.runtime.cancellation import CancellationSource, TaskCancelled


@dataclass(frozen=True, slots=True)
class AttachmentJob:
    key: str
    name: str
    cancellation: CancellationSource
    path: Path | None = None
    image: QImage | None = None


class AttachmentPreparationWorker(QObject):
    prepared = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(str, str)
    done = Signal()

    def __init__(self, store, jobs, *, cloud=False):
        super().__init__()
        self.store, self.jobs = store, tuple(jobs)
        self.cloud = cloud

    @Slot()
    def run(self):
        try:
            for job in self.jobs:
                token = job.cancellation.token
                try:
                    token.raise_if_cancelled()
                    self.progress.emit(job.key, "Copying…")
                    if job.path is not None:
                        reference = self.store.import_file(job.path, cancellation=token)
                    else:
                        if job.image.width() * job.image.height() > MAX_IMAGE_PIXELS:
                            from app.inference.attachments import AttachmentError
                            raise AttachmentError("The clipboard image is too large to process safely.")
                        buffer = QBuffer()
                        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                        if not job.image.save(buffer, "PNG"):
                            raise ValueError("Clipboard image conversion failed.")
                        reference = self.store.import_bytes(bytes(buffer.data()), name=job.name, cancellation=token)
                    self.progress.emit(job.key, "Preparing…")
                    if self.cloud:
                        from app.conversation.cloud_attachments import prepare_cloud_attachment
                        prepared = prepare_cloud_attachment(self.store, reference, cancellation=token)
                    else:
                        prepared = AttachmentProcessor(self.store).prepare(reference, cancellation=token)
                    self.prepared.emit(job.key, prepared)
                except TaskCancelled:
                    pass
                except Exception as exc:
                    from app.inference.attachments import AttachmentError
                    self.failed.emit(job.key, str(exc) if isinstance(exc, AttachmentError) else
                                     "The attachment could not be prepared. Try another file.")
        finally:
            self.done.emit()


class AttachmentTray(QWidget):
    changed = Signal()
    idle = Signal()
    notice = Signal(str)

    def __init__(self, store, mode, parent=None):
        super().__init__(parent)
        self.store, self.mode = store, mode
        self._entries = {}
        self._queued = []
        self.thread = self.worker = None
        self._closing = False
        self._editable = True
        self.setObjectName("attachmentTray")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 2)
        layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedHeight(66)
        self.content = QWidget()
        self.cards = QHBoxLayout(self.content)
        self.cards.setContentsMargins(0, 0, 0, 0)
        self.cards.setSpacing(6)
        self.cards.addStretch()
        scroll.setWidget(self.content)
        layout.addWidget(scroll)
        self.hide()

    @property
    def references(self):
        return tuple(entry["prepared"].reference for entry in self._entries.values() if entry["prepared"] is not None)

    @property
    def count(self):
        return len(self._entries)

    @property
    def is_processing(self):
        return self.thread is not None

    @property
    def ready(self):
        return all(entry["prepared"] is not None for entry in self._entries.values()) and not (
            self.mode() == "local" and self.count > 1)

    def add_paths(self, paths):
        jobs = [AttachmentJob(uuid4().hex, Path(path).name, CancellationSource(), path=Path(path)) for path in paths]
        self._add(jobs)

    def add_mime(self, mime):
        if mime.hasUrls() and all(url.isLocalFile() for url in mime.urls()):
            self.add_paths([url.toLocalFile() for url in mime.urls()])
        elif mime.hasImage():
            image = mime.imageData()
            if isinstance(image, QPixmap):
                image = image.toImage()
            if not isinstance(image, QImage) or image.isNull():
                self.notice.emit("The clipboard image is unreadable.")
                return
            self._add([AttachmentJob(uuid4().hex, "Clipboard image.png", CancellationSource(), image=image.copy())])
        else:
            self.notice.emit("Drop local files or paste an image. Remote links can be pasted as text.")

    def _add(self, jobs):
        if not jobs or not self._editable or self._closing or self.store is None:
            return
        if self.mode() == "local" and self.count + len(jobs) > 1:
            self.notice.emit("Local mode allows one file or image per message. Remove the current attachment first.")
            return
        for job in jobs:
            card = QFrame()
            card.setObjectName("attachmentCard")
            card.setFixedSize(235, 56)
            row = QHBoxLayout(card)
            row.setContentsMargins(8, 5, 5, 5)
            row.setSpacing(7)
            preview = QLabel("FILE")
            preview.setObjectName("attachmentPreview")
            preview.setFixedSize(40, 40)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(preview)
            labels = QVBoxLayout()
            labels.setContentsMargins(0, 0, 0, 0)
            labels.setSpacing(1)
            name, status = QLabel(), QLabel("Preparing…")
            name.setTextFormat(Qt.TextFormat.PlainText)
            status.setTextFormat(Qt.TextFormat.PlainText)
            name.setObjectName("attachmentName")
            status.setObjectName("attachmentDetail")
            name.setText(name.fontMetrics().elidedText(job.name, Qt.TextElideMode.ElideMiddle, 142))
            card.setToolTip("<qt>" + escape(job.name) + "</qt>")
            labels.addWidget(name)
            labels.addWidget(status)
            row.addLayout(labels, 1)
            remove = QPushButton("×")
            remove.setObjectName("attachmentRemove")
            remove.setFixedSize(22, 22)
            remove.setAccessibleName("Remove " + job.name)
            remove.clicked.connect(lambda checked=False, key=job.key: self.remove(key))
            row.addWidget(remove)
            self.cards.insertWidget(self.cards.count() - 1, card)
            self._entries[job.key] = dict(job=job, card=card, preview=preview, status=status, remove=remove, prepared=None)
            self._queued.append(job)
        self.show()
        self.changed.emit()
        self._start()

    def _start(self):
        if self.thread is not None or not self._queued or self._closing:
            return
        jobs, self._queued = tuple(self._queued), []
        self.thread = QThread()
        self.worker = AttachmentPreparationWorker(self.store, jobs, cloud=self.mode() == "cloud")
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.prepared.connect(self._prepared)
        self.worker.failed.connect(self._failed)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self.thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._finished)
        self.thread.start()

    @Slot(str, object)
    def _prepared(self, key, prepared):
        entry = self._entries.get(key)
        if entry is None or self._closing:
            return
        entry["prepared"] = prepared
        detail = prepared.processed.summary
        entry["status"].setText(entry["status"].fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, 142))
        tooltip = entry["job"].name + "\n" + detail + "\n" + "\n".join(prepared.processed.warnings)
        entry["card"].setToolTip("<qt>" + escape(tooltip).replace("\n", "<br/>") + "</qt>")
        if prepared.thumbnail is not None:
            entry["preview"].setPixmap(QPixmap.fromImage(prepared.thumbnail).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.changed.emit()

    @Slot(str, str)
    def _progress(self, key, status):
        if key in self._entries:
            self._entries[key]["status"].setText(status)

    @Slot(str, str)
    def _failed(self, key, error):
        if key not in self._entries or self._closing:
            return
        entry = self._entries[key]
        entry["status"].setText("Could not prepare")
        entry["card"].setToolTip("<qt>" + escape(entry["job"].name + "\n" + error).replace("\n", "<br/>") + "</qt>")
        self.notice.emit(error)
        self.changed.emit()

    @Slot()
    def _finished(self):
        self.thread.deleteLater()
        self.thread = self.worker = None
        self._start()
        if self.thread is None:
            self.idle.emit()

    def remove(self, key):
        entry = self._entries.pop(key, None)
        if entry is None:
            return
        entry["job"].cancellation.cancel()
        self.cards.removeWidget(entry["card"])
        entry["card"].deleteLater()
        self.setVisible(bool(self._entries))
        self.changed.emit()

    def clear(self):
        for key in tuple(self._entries):
            self.remove(key)

    def set_editable(self, editable):
        self._editable = editable
        for entry in self._entries.values():
            entry["remove"].setEnabled(editable)

    def shutdown(self):
        self._closing = True
        self._queued.clear()
        for entry in self._entries.values():
            entry["job"].cancellation.cancel()
