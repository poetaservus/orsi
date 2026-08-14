from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.agent_runtime import AgentRunStatus, AgentRuntime
from app.conversation.prompt import AGENT_SYSTEM_PROMPT, SYSTEM_PROMPT
from app.conversation.store import ConversationStore
from app.runtime.cancellation import CancellationSource, TaskCancelled


class ConversationService:
    """UI-facing private conversation with an optional bounded agent loop."""

    def __init__(
        self,
        inference,
        store: ConversationStore,
        *,
        agent_runtime: AgentRuntime | None = None,
        portable_root: Path | None = None,
        allowed_read_roots: tuple[Path, ...] = (),
        agent_error: str | None = None,
    ):
        if agent_runtime is not None and not isinstance(agent_runtime, AgentRuntime):
            raise TypeError("The conversation agent must be an AgentRuntime.")
        if agent_runtime is not None and not isinstance(portable_root, Path):
            raise TypeError("Agent conversations require a pathlib.Path portable root.")
        if not all(isinstance(root, Path) for root in allowed_read_roots):
            raise TypeError("Agent read roots must be pathlib.Path values.")
        self.inference = inference
        self.store = store
        self.agent_runtime = agent_runtime
        self.portable_root = portable_root
        self.allowed_read_roots = (
            allowed_read_roots
            if allowed_read_roots
            else ((portable_root,) if portable_root is not None else ())
        )
        self.agent_error = str(agent_error).strip() if agent_error else None
        self._run_lock = Lock()
        self._cancellation_lock = Lock()
        self._cancellation: CancellationSource | None = None
        self._session_id = uuid4().hex
        self._turn_number = 0

    @property
    def agent_enabled(self) -> bool:
        return self.agent_runtime is not None

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
                activity("Working..." if self.agent_enabled else "Thinking...")
            source.token.raise_if_cancelled()
            if self.agent_runtime is None:
                response = self.inference.respond(self._model_messages())
                source.token.raise_if_cancelled()
                if not isinstance(response, str) or not response.strip():
                    raise RuntimeError("The model returned an empty response.")
                answer = response.strip()
            else:
                self._turn_number += 1
                result = self.agent_runtime.run(
                    self._model_messages(),
                    session_id=self._session_id,
                    turn_id=f"turn-{self._turn_number}",
                    portable_root=self.portable_root,
                    allowed_read_roots=self.allowed_read_roots,
                    cancellation=source.token,
                )
                if result.status == AgentRunStatus.CANCELLED:
                    return "The response was stopped."
                if result.status != AgentRunStatus.COMPLETED:
                    raise RuntimeError(
                        result.message or "The bounded agent run did not complete."
                    )
                answer = result.assistant_text.strip()
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
            if self.agent_runtime is not None:
                self.agent_runtime.purge_terminal_records()
            self.store.new_session()
            self._session_id = uuid4().hex
            self._turn_number = 0
        finally:
            self._run_lock.release()

    def shutdown(self) -> None:
        self.cancel_current_task()
        if self.agent_runtime is not None:
            self.agent_runtime.shutdown()
        close = getattr(self.inference, "close", None)
        if callable(close):
            close()

    def estimated_context_tokens(self) -> int:
        if not self.store.messages():
            return 0
        prompt_tokens = self._count_tokens(self._model_messages())
        return min(self._context_length(), prompt_tokens + self._response_reserve())

    def _model_messages(self) -> list[dict[str, str]]:
        prompt = AGENT_SYSTEM_PROMPT if self.agent_enabled else SYSTEM_PROMPT
        system = {"role": "system", "content": prompt}
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
