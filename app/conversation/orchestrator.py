from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.agent.runtime import AgentRunStatus, AgentRuntime
from app.conversation.context import (
    capability_schema_reserve,
    context_length,
    count_message_tokens,
    estimated_context_tokens,
    response_reserve,
    select_context_messages,
)
from app.conversation.capability_routing import select_turn_capabilities
from app.conversation.prompt import (
    AGENT_CONVERSATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    agent_system_prompt,
    compact_agent_system_prompt,
)
from app.conversation.result_grounding import grounded_text_read_answer
from app.conversation.store import ConversationStore
from app.security.host_access import HostAccessPolicy, HostReadScope
from app.inference.protocol import (
    model_capability_calls_message,
    model_capability_result_message,
)
from app.runtime.cancellation import CancellationSource, TaskCancelled


class ConversationService:
    """UI-facing conversation session and the sole owner of agent turn lifecycle."""

    def __init__(
        self,
        inference,
        store: ConversationStore,
        *,
        agent_runtime: AgentRuntime | None = None,
        portable_root: Path | None = None,
        allowed_read_roots: tuple[Path, ...] = (),
        host_access_policy: HostAccessPolicy | None = None,
        agent_error: str | None = None,
    ):
        if agent_runtime is not None and not isinstance(agent_runtime, AgentRuntime):
            raise TypeError("The conversation agent must be an AgentRuntime.")
        if agent_runtime is not None and not isinstance(portable_root, Path):
            raise TypeError("Agent conversations require a pathlib.Path portable root.")
        if not all(isinstance(root, Path) for root in allowed_read_roots):
            raise TypeError("Agent read roots must be pathlib.Path values.")
        if host_access_policy is not None and not isinstance(
            host_access_policy,
            HostAccessPolicy,
        ):
            raise TypeError("Conversation host access must be a HostAccessPolicy.")

        self.inference = inference
        self.store = store
        self.agent_runtime = agent_runtime
        self.portable_root = portable_root
        self.allowed_read_roots = (
            allowed_read_roots
            if allowed_read_roots
            else ((portable_root,) if portable_root is not None else ())
        )
        self.host_access_policy = (
            host_access_policy
            if host_access_policy is not None
            else (
                HostAccessPolicy.portable_root(portable_root)
                if agent_runtime is not None
                else None
            )
        )
        self.agent_error = str(agent_error).strip() if agent_error else None
        self._run_lock = Lock()
        self._cancellation_lock = Lock()
        self._cancellation: CancellationSource | None = None
        self._session_id = uuid4().hex
        self._turn_number = 0
        # Capability calls/results stay in memory. Persistent history intentionally
        # contains only the user-visible conversation.
        self._agent_history = self.store.messages()

    @property
    def agent_enabled(self) -> bool:
        return self.agent_runtime is not None

    @property
    def host_read_scope(self) -> HostReadScope | None:
        if self.host_access_policy is None:
            return None
        return self.host_access_policy.read_scope

    @property
    def agent_capabilities(self) -> tuple[str, ...]:
        if self.agent_runtime is None:
            return ()
        return self.agent_runtime.registry.model_visible_names

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
            if self.agent_runtime is None:
                answer = self._run_chat_turn(source, activity)
                self.store.append("assistant", answer)
                return answer

            self._agent_history.append({"role": "user", "content": text})
            answer, turn_trace = self._run_agent_turn(text, source, activity)
            self.store.append("assistant", answer)
            self._agent_history.extend(deepcopy(turn_trace))
            self._agent_history.append({"role": "assistant", "content": answer})
            return answer
        except TaskCancelled:
            return "The response was stopped."
        finally:
            with self._cancellation_lock:
                if self._cancellation is source:
                    self._cancellation = None
            self._run_lock.release()

    def _run_chat_turn(self, source: CancellationSource, activity=None) -> str:
        if activity:
            activity("Thinking...")
        source.token.raise_if_cancelled()
        response = self.inference.respond(self._model_messages(capability_turn=False))
        source.token.raise_if_cancelled()
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("The model returned an empty response.")
        return response.strip()

    def _run_agent_turn(
        self,
        text: str,
        source: CancellationSource,
        activity=None,
    ) -> tuple[str, list[dict]]:
        if self.agent_runtime is None or self.portable_root is None:
            raise RuntimeError("The structured agent runtime is unavailable.")
        if activity:
            activity("Working...")
        source.token.raise_if_cancelled()
        self._turn_number += 1
        turn_trace: list[dict] = []
        turn_results: list[tuple] = []

        def retain_results(calls, results) -> None:
            turn_trace.append(model_capability_calls_message(calls))
            turn_trace.extend(
                model_capability_result_message(
                    call,
                    result.model_dump(mode="json"),
                )
                for call, result in zip(calls, results, strict=True)
            )
            turn_results.extend(zip(calls, results, strict=True))

        capabilities = self._turn_capabilities(text)
        result = self.agent_runtime.run(
            self._model_messages(
                capability_turn=True,
                capability_names=capabilities,
            ),
            session_id=self._session_id,
            turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            result_observer=retain_results,
            capability_names=capabilities,
        )
        if result.status == AgentRunStatus.CANCELLED:
            raise TaskCancelled("The response was stopped.")
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "The bounded agent run did not complete.")

        answer = result.assistant_text.strip()
        grounded_answer = grounded_text_read_answer(text, answer, turn_results)
        if grounded_answer is not None:
            answer = grounded_answer
        return answer, turn_trace

    def set_approval_requester(self, requester) -> None:
        if self.agent_runtime is not None:
            self.agent_runtime.set_approval_requester(requester)

    def resolve_approval(self, approval_id: str, approved: bool) -> None:
        if self.agent_runtime is not None:
            self.agent_runtime.resolve_approval(approval_id, approved)

    def approval_status(self, approval_id: str) -> str | None:
        if self.agent_runtime is None:
            return None
        return self.agent_runtime.approval_status(approval_id)

    def cancel_current_task(self) -> bool:
        with self._cancellation_lock:
            source = self._cancellation
        if source is None:
            return False
        source.cancel("The response was stopped.")
        return True

    def new_session(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Stop the current response before starting a new session.")
        try:
            self.store.new_session()
            if self.agent_runtime is not None:
                self.agent_runtime.purge_terminal_records()
            self._session_id = uuid4().hex
            self._turn_number = 0
            self._agent_history = []
        finally:
            self._run_lock.release()

    def shutdown(self) -> None:
        self.cancel_current_task()
        if self.agent_runtime is not None:
            close = getattr(self.agent_runtime, "shutdown", None)
            if callable(close):
                close()

    def estimated_context_tokens(self) -> int:
        if not self.store.messages():
            return 0
        capabilities = self.agent_capabilities
        if self.agent_enabled:
            latest_user = next(
                (
                    message.get("content", "")
                    for message in reversed(self._agent_history)
                    if message.get("role") == "user"
                ),
                "",
            )
            capabilities = self._turn_capabilities(latest_user)
        messages = self._model_messages(
            capability_turn=self.agent_enabled,
            capability_names=(capabilities if self.agent_enabled else None),
        )
        return estimated_context_tokens(
            self.inference,
            messages,
            reserved_tokens=self._capability_schema_reserve(capabilities),
        )

    def _model_messages(
        self,
        *,
        capability_turn: bool | None = None,
        capability_names: tuple[str, ...] | None = None,
    ) -> list[dict]:
        use_agent = self.agent_enabled and capability_turn is not False
        capabilities = (
            self.agent_capabilities if capability_names is None else capability_names
        )
        schema_reserve = 0
        if use_agent:
            schema_reserve = self._capability_schema_reserve(capabilities)
            prompt = agent_system_prompt(
                self.host_read_scope or HostReadScope.PORTABLE_ROOT,
                capabilities,
                user_home=(
                    str(self.host_access_policy.user_home)
                    if self.host_access_policy is not None
                    else None
                ),
            )
            full_system = {"role": "system", "content": prompt}
            count_message_tokens(self.inference, [full_system])
            budget = max(
                1,
                context_length(self.inference)
                - response_reserve(self.inference)
                - schema_reserve,
            )
            if count_message_tokens(self.inference, [full_system]) >= max(1, budget - 256):
                prompt = compact_agent_system_prompt(
                    self.host_read_scope or HostReadScope.PORTABLE_ROOT,
                    capabilities,
                    user_home=(
                        str(self.host_access_policy.user_home)
                        if self.host_access_policy is not None
                        else None
                    ),
                )
            history = self._agent_history
        else:
            prompt = AGENT_CONVERSATION_SYSTEM_PROMPT if self.agent_enabled else SYSTEM_PROMPT
            history = self.store.messages()
        return select_context_messages(
            self.inference,
            system_prompt=prompt,
            history=history,
            reserved_tokens=schema_reserve,
        )

    def _planner_capabilities(self) -> tuple[str, ...]:
        """Return the full registry catalog without applying semantic routing."""
        return self.agent_capabilities

    def _turn_capabilities(self, latest_user_text: str) -> tuple[str, ...]:
        if self.agent_runtime is None:
            return ()
        available = self.agent_capabilities
        selected = set(select_turn_capabilities(latest_user_text, available))
        history_names = self._history_capability_names()
        selected.update(history_names)
        if self._has_filesystem_followup_context() and (
            re.fullmatch(
                r"\s*(?:yes|yeah|yep|ok(?:ay)?|go ahead|do it|there|the rest|remaining)"
                r"\s*[.!?]*\s*",
                latest_user_text,
                flags=re.IGNORECASE,
            )
            or re.fullmatch(r"\s*[A-Za-z]:[\\/].+", latest_user_text)
        ):
            selected.update(available)
        return tuple(name for name in available if name in selected)

    def _history_capability_names(self) -> set[str]:
        available = set(self.agent_capabilities)
        names: set[str] = set()
        for message in self._agent_history:
            if message.get("role") != "assistant":
                continue
            calls = message.get("capability_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if isinstance(call, dict) and call.get("capability") in available:
                    names.add(call["capability"])
        return names

    def _has_filesystem_followup_context(self) -> bool:
        for message in reversed(self._agent_history[-8:]):
            content = message.get("content")
            if isinstance(content, str) and re.search(
                r"\b(?:file|folder|directory|path|desktop|documents|downloads)\b",
                content,
                flags=re.IGNORECASE,
            ):
                return True
        return False

    def _capability_schema_reserve(self, names: tuple[str, ...]) -> int:
        if self.agent_runtime is None or not names:
            return 0
        selected = set(names)
        definitions = tuple(
            definition
            for definition in self.agent_runtime.registry.model_definitions()
            if definition.name in selected
        )
        return capability_schema_reserve(definitions)
