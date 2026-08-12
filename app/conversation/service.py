from __future__ import annotations

from threading import Lock

from app.conversation.prompt import SYSTEM_PROMPT
from app.conversation.store import ConversationStore
from app.runtime.cancellation import CancellationSource, TaskCancelled


class ConversationService:
    """UI-facing chat loop: save text, ask the model, save text."""

    def __init__(self, inference, store: ConversationStore, *, history_max_chars: int = 40_000):
        self.inference = inference
        self.store = store
        self.history_max_chars = max(1_000, int(history_max_chars))
        self._run_lock = Lock()
        self._cancellation_lock = Lock()
        self._cancellation: CancellationSource | None = None

    def run(self, user_message: str, activity=None) -> str:
        text = str(user_message).strip()
        if not text:
            raise ValueError("Enter a message first.")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("O.R.S.I is already replying.")
        source = CancellationSource()
        with self._cancellation_lock:
            self._cancellation = source
        try:
            self.store.append("user", text)
            if activity:
                activity("Thinking...")
            source.token.raise_if_cancelled()
            response = self.inference.respond(self._model_messages())
            source.token.raise_if_cancelled()
            if not isinstance(response, str) or not response.strip():
                raise RuntimeError("The model returned an empty response.")
            answer = response.strip()
            self.store.append("assistant", answer)
            return answer
        except TaskCancelled:
            return "The response was stopped."
        finally:
            with self._cancellation_lock:
                if self._cancellation is source:
                    self._cancellation = None
            self._run_lock.release()

    def cancel_current_task(self) -> bool:
        with self._cancellation_lock:
            source = self._cancellation
        if source is None:
            return False
        source.cancel("The response was stopped.")
        return True

    def _model_messages(self) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        used = 0
        for message in reversed(self.store.messages()):
            content = message["content"]
            remaining = self.history_max_chars - used
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[: max(0, remaining - len("[TRUNCATED]"))] + "[TRUNCATED]"
            selected.append({"role": message["role"], "content": content})
            used += len(content)
        selected.reverse()
        return [{"role": "system", "content": SYSTEM_PROMPT}, *selected]
