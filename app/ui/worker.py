from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot
from app.inference.completion import CompletionText, IncompleteResponseError
from app.inference.attachments import attachment_references


log = logging.getLogger(__name__)


class ConversationWorker(QObject):
    """Run one conversation turn away from the GUI event loop."""

    finished = Signal(object)
    failed = Signal(object)
    activity = Signal(str)
    text_updated = Signal(str)
    skill_used = Signal(str)

    def __init__(self, service, message: str, *, skill_name: str | None = None, attachments=()):
        super().__init__()
        self.service = service
        self.message = message
        self.skill_name = skill_name
        self.attachments = attachment_references(attachments)

    @Slot()
    def run(self) -> None:
        try:
            kwargs = {}
            if self.attachments:
                kwargs["attachments"] = self.attachments
            if self.skill_name is not None:
                kwargs["skill_name"] = self.skill_name
            if getattr(self.service, "supports_text_streaming", False) is True:
                kwargs["text_observer"] = self.text_updated.emit
            if getattr(self.service, "supports_skill_reporting", False) is True:
                kwargs["skill_observer"] = self.skill_used.emit
            response = self.service.run(self.message, self.activity.emit, **kwargs)
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
