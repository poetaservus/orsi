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
    admitted = Signal()
    draft_rejected = Signal()

    def __init__(self, service, message: str, *, skill_name: str | None = None, attachments=()):
        super().__init__()
        self.service = service
        self.message = message
        self.skill_name = skill_name
        self.attachments = attachment_references(attachments)
        self._admitted = False

    def _mark_admitted(self):
        self._admitted = True
        self.admitted.emit()

    def _restore_unadmitted(self):
        if self.attachments and not self._admitted and getattr(self.service, 'supports_admission_reporting', False) is True:
            self.draft_rejected.emit()

    @Slot()
    def run(self) -> None:
        try:
            kwargs = {}
            if self.attachments:
                kwargs["attachments"] = self.attachments
                if getattr(self.service, 'supports_admission_reporting', False) is True:
                    kwargs['admission_observer'] = self._mark_admitted
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
            self._restore_unadmitted()
            self.finished.emit(response)
        except IncompleteResponseError as exc:
            self._restore_unadmitted()
            self.failed.emit(CompletionText(exc.partial_text or str(exc), exc.completion,
                exc.completion_history, status_message=str(exc) if exc.partial_text else None))
        except Exception as exc:
            self._restore_unadmitted()
            log.exception("A conversation turn failed in the UI worker.")
            from app.vault.types import VaultError
            from app.vault.profiles import public_error
            self.failed.emit(public_error(exc) if isinstance(exc, VaultError) else str(exc))


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
