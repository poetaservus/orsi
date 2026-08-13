from __future__ import annotations

from threading import Lock

from app.conversation.prompt import SYSTEM_PROMPT
from app.conversation.store import ConversationStore
from app.runtime.cancellation import CancellationSource, TaskCancelled


class ConversationService:
    """UI-facing chat loop: save text, ask the model, save text."""

    def __init__(self, inference, store: ConversationStore):
        self.inference = inference
        self.store = store
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

    def new_session(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Wait for the current response to finish before starting a new session.")
        try:
            self.store.new_session()
        finally:
            self._run_lock.release()

    def estimated_context_tokens(self) -> int:
        if not self.store.messages():
            return 0
        prompt_tokens = self._count_tokens(self._model_messages())
        return min(self._context_length(), prompt_tokens + self._response_reserve())

    def _model_messages(self) -> list[dict[str, str]]:
        system = {"role": "system", "content": SYSTEM_PROMPT}
        # Token counting may lazily load the local model and replace the
        # startup context hint with the context it could actually allocate.
        self._count_tokens([system])
        prompt_budget = max(1, self._context_length() - self._response_reserve())
        selected: list[dict[str, str]] = []
        for message in reversed(self.store.messages()):
            candidate_message = {"role": message["role"], "content": message["content"]}
            candidate = [system, candidate_message, *selected]
            if self._count_tokens(candidate) <= prompt_budget:
                selected.insert(0, candidate_message)
                continue

            truncated = self._largest_fitting_suffix(
                system,
                candidate_message,
                selected,
                prompt_budget,
            )
            if truncated is not None:
                selected.insert(0, truncated)
            break
        return [system, *selected]

    def _largest_fitting_suffix(self, system, message, selected, budget):
        marker = "[Earlier content truncated]\n"
        content = message["content"]
        low, high = 0, len(content)
        best = None
        while low <= high:
            keep = (low + high) // 2
            shortened = marker + (content[-keep:] if keep else "")
            candidate_message = {"role": message["role"], "content": shortened}
            if self._count_tokens([system, candidate_message, *selected]) <= budget:
                best = candidate_message
                low = keep + 1
            else:
                high = keep - 1
        return best

    def _count_tokens(self, messages: list[dict[str, str]]) -> int:
        counter = getattr(self.inference, "count_message_tokens", None)
        if callable(counter):
            return max(1, int(counter(messages)))
        characters = sum(len(message["content"]) for message in messages)
        return max(1, (characters + 3) // 4 + 4 * len(messages) + 3)

    def _context_length(self) -> int:
        return max(512, int(getattr(self.inference, "context_length", 8192)))

    def _response_reserve(self) -> int:
        configured = max(32, int(getattr(self.inference, "max_response_tokens", 512)))
        return min(configured, self._context_length() // 2)
