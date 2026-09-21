from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot


log = logging.getLogger(__name__)


class ConversationWorker(QObject):
    """Run one conversation turn away from the GUI event loop."""

    finished = Signal(str)
    failed = Signal(str)
    activity = Signal(str)

    def __init__(self, service, message: str):
        super().__init__()
        self.service = service
        self.message = message

    @Slot()
    def run(self) -> None:
        try:
            response = self.service.run(self.message, self.activity.emit)
            if response is None or not str(response).strip():
                raise RuntimeError("O.R.S.I finished processing, but returned an empty response.")
            self.finished.emit(str(response))
        except Exception as exc:
            log.exception("A conversation turn failed in the UI worker.")
            self.failed.emit(str(exc))
