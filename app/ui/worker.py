from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot
from app.inference.completion import CompletionText, IncompleteResponseError


log = logging.getLogger(__name__)


class ConversationWorker(QObject):
    """Run one conversation turn away from the GUI event loop."""

    finished = Signal(object)
    failed = Signal(object)
    activity = Signal(str)

    def __init__(self, service, message: str, *, skill_name: str | None = None):
        super().__init__()
        self.service = service
        self.message = message
        self.skill_name = skill_name

    @Slot()
    def run(self) -> None:
        try:
            if self.skill_name is None:
                response = self.service.run(self.message, self.activity.emit)
            else:
                response = self.service.run(self.message, self.activity.emit, skill_name=self.skill_name)
            if isinstance(response, str) and getattr(response, "completion", None) is not None:
                if response.completion.incomplete and not response.strip():
                    raise IncompleteResponseError("The response was cut off.", response.completion,
                                                  history=response.completion_history)
            if response is None or not str(response).strip():
                raise RuntimeError("O.R.S.I finished processing, but returned an empty response.")
            self.finished.emit(response)
        except IncompleteResponseError as exc:
            self.failed.emit(CompletionText(exc.partial_text or str(exc), exc.completion,
                exc.completion_history, status_message=str(exc) if exc.partial_text else None))
        except Exception as exc:
            log.exception("A conversation turn failed in the UI worker.")
            self.failed.emit(str(exc))


class ModelSwitchWorker(QObject):
    finished = Signal()
    failed = Signal(str)

    def __init__(self, service, model_id: str):
        super().__init__()
        self.service, self.model_id = service, model_id

    @Slot()
    def run(self):
        try:
            self.service.select_local_model(self.model_id)
            self.finished.emit()
        except Exception as exc:
            log.warning("Local model selection failed: %s", type(exc).__name__)
            self.failed.emit(str(exc))
