from __future__ import annotations

import logging
import re
from copy import deepcopy
from pathlib import Path
from threading import Lock

from app.agent.runtime import AgentRunStatus, AgentRuntime
from app.agent.contracts import AgentRunResult, SettledCall
from app.conversation.context import (
    DEFAULT_SAFETY_BUFFER_TOKENS,
    ContextBudget,
    ContextSelection,
    capability_schema_reserve,
    context_length,
    count_message_tokens,
    empty_context_budget,
    response_reserve,
    select_context_request,
)
from app.conversation.capability_routing import select_turn_capabilities
from app.conversation.prompt import (
    AGENT_CONVERSATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    agent_system_prompt,
    compact_agent_system_prompt,
)
from app.conversation.result_grounding import grounded_text_read_answer
from app.conversation.store import ConversationStore, TurnHistoryError
from app.security.host_access import HostAccessPolicy, HostReadScope
from app.inference.engine import InferenceUnavailable
from app.inference.diagnostics import record_context_budget
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.inference.completion import CompletionText, IncompleteResponseError


log = logging.getLogger(__name__)


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
        self._closed = False
        self._session_id = self.store.session_id
        self._active_turn_id: str | None = None
        self._turn_result: AgentRunResult | None = None
        self._history_persistence_failed = False
        if agent_runtime is not None:
            self.store.reconcile_journal(agent_runtime.executor.journal.records)
        self._agent_history = self.store.agent_messages(capability_names=self.agent_capabilities)

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
        turn_id = None
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
                self._cancellation = source
            if self._history_persistence_failed:
                raise TurnHistoryError("A settled turn could not be retained safely. Review its outcomes before retrying.")
            turn_id = self.store.begin_turn(text)
            self._active_turn_id = turn_id
            self._turn_result = None
            self._agent_history.append({"role": "user", "content": text})
            if self.agent_runtime is None:
                answer = self._run_chat_turn(source, activity)
                value = CompletionText(answer)
                self._turn_result = AgentRunResult(
                    status=AgentRunStatus.INCOMPLETE if value.completion.incomplete else AgentRunStatus.COMPLETED,
                    assistant_text=None if value.completion.incomplete else str(value),
                    partial_text=str(value) if value.completion.incomplete else None,
                    message="The response is incomplete." if value.completion.incomplete else None,
                    steps=1, capability_calls=0, protocol_failures=0,
                    model_requests=1,
                    completion=value.completion, completion_history=value.completion_history)
            else:
                answer = self._run_agent_turn(text, source, activity)
            self.store.finish_turn(turn_id, self._turn_result, answer)
            self._agent_history = self.store.agent_messages(capability_names=self.agent_capabilities)
            return answer
        except Exception as exc:
            if turn_id is not None:
                outcome = self._turn_result
                if outcome is None or outcome.status == AgentRunStatus.COMPLETED:
                    prior_outcome = outcome
                    value = CompletionText(exc.partial_text or "", exc.completion, exc.completion_history) \
                        if isinstance(exc, IncompleteResponseError) else CompletionText("")
                    status = (AgentRunStatus.CANCELLED if isinstance(exc, TaskCancelled) else
                              AgentRunStatus.INCOMPLETE if isinstance(exc, IncompleteResponseError) else
                              AgentRunStatus.MODEL_UNAVAILABLE if isinstance(exc, InferenceUnavailable) else
                              AgentRunStatus.INTERNAL_FAILURE)
                    outcome = AgentRunResult(status=status, message=str(exc).strip()[:500] or "The turn stopped.",
                        steps=prior_outcome.steps if prior_outcome else 0,
                        capability_calls=prior_outcome.capability_calls if prior_outcome else 0,
                        protocol_failures=prior_outcome.protocol_failures if prior_outcome else 0,
                        model_requests=prior_outcome.model_requests if prior_outcome else 0,
                        consecutive_format_failures=prior_outcome.consecutive_format_failures if prior_outcome else 0,
                        semantic_corrections=prior_outcome.semantic_corrections if prior_outcome else 0,
                        completion=prior_outcome.completion if prior_outcome else value.completion,
                        completion_history=prior_outcome.completion_history if prior_outcome else value.completion_history,
                        partial_text=prior_outcome.assistant_text if prior_outcome else str(value) or None,
                        settled_calls=prior_outcome.settled_calls if prior_outcome else ())
                try:
                    self.store.finish_turn(turn_id, outcome)
                    self._agent_history = self.store.agent_messages(capability_names=self.agent_capabilities)
                except Exception:
                    self._history_persistence_failed = True
                    self._agent_history.append({"role": "assistant", "content":
                        f"Turn stopped ({outcome.status.value}). {outcome.message or 'History persistence failed.'}"})
                    log.exception("Stopped turn outcomes could not be persisted.")
                if isinstance(exc, TurnHistoryError):
                    self._history_persistence_failed = True
            if isinstance(exc, TaskCancelled):
                return "The response was stopped."
            raise
        finally:
            with self._cancellation_lock:
                if self._cancellation is source:
                    self._cancellation = None
            self._active_turn_id = None
            self._run_lock.release()

    def _run_chat_turn(self, source: CancellationSource, activity=None) -> str:
        if activity:
            activity("Thinking...")
        source.token.raise_if_cancelled()
        request = self._model_request(capability_turn=False)
        if not request.budget.fits:
            raise RuntimeError("The conversation cannot fit the active model context window.")
        record_context_budget(log, request.budget, request_kind="conversation")
        response = self.inference.respond(request.messages)
        source.token.raise_if_cancelled()
        if isinstance(response, str) and getattr(response, "completion", None) is not None:
            if response.completion.incomplete and not response.strip():
                raise IncompleteResponseError("The response was cut off.", response.completion,
                                              history=response.completion_history)
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("The model returned an empty response.")
        text = CompletionText(response)
        return CompletionText(str(text) if text.completion.incomplete else text.strip(),
                              text.completion, text.completion_history)

    def _run_agent_turn(
        self,
        text: str,
        source: CancellationSource,
        activity=None,
    ) -> str:
        if self.agent_runtime is None or self.portable_root is None:
            raise RuntimeError("The structured agent runtime is unavailable.")
        if activity:
            activity("Working...")
        source.token.raise_if_cancelled()
        turn_results: list[tuple] = []

        def retain_settled(settled: SettledCall) -> None:
            self._agent_history.extend(deepcopy(settled.messages()))
            turn_results.append((settled.call, settled.result))
            try:
                self.store.record_settled(self._active_turn_id, settled)
            except Exception:
                self._history_persistence_failed = True
                raise

        capabilities = self._turn_capabilities(text)
        request = self._model_request(
            capability_turn=True,
            capability_names=capabilities,
        )
        if not request.budget.fits:
            raise RuntimeError("The agent request cannot fit the active model context window.")
        result = self.agent_runtime.run(
            request.messages,
            session_id=self._session_id,
            turn_id=self._active_turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            settled_observer=retain_settled,
            capability_names=capabilities,
        )
        self._turn_result = result
        if result.status == AgentRunStatus.CANCELLED:
            raise TaskCancelled("The response was stopped.")
        if result.status == AgentRunStatus.INCOMPLETE:
            if result.partial_text is not None:
                return CompletionText(result.partial_text, result.completion, result.completion_history,
                                      status_message=result.message)
            raise IncompleteResponseError(result.message or "The response is incomplete.",
                result.completion, history=result.completion_history)
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "The bounded agent run did not complete.")

        answer = result.assistant_text.strip()
        grounded_answer = grounded_text_read_answer(text, answer, turn_results)
        if grounded_answer is not None:
            answer = grounded_answer
        return CompletionText(answer, result.completion, result.completion_history)

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
            self._session_id = self.store.session_id
            self._history_persistence_failed = False
            self._agent_history = []
            if self.agent_runtime is not None:
                self.agent_runtime.purge_terminal_records()
        finally:
            self._run_lock.release()

    def select_local_model(self, model_id: str) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Finish or stop the current response before switching models.")
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
            self.inference.select_local_model(model_id)
        finally:
            self._run_lock.release()

    def shutdown(self) -> None:
        with self._cancellation_lock:
            if self._closed:
                return
            self._closed = True
        try:
            self.cancel_current_task()
        finally:
            try:
                self.store.close_session()
            except Exception:
                log.exception("Session close outcome could not be persisted.")
            try:
                close = getattr(self.inference, "close", None)
                if callable(close):
                    close()
            finally:
                close = getattr(self.agent_runtime, "shutdown", None)
                if callable(close):
                    close()

    def estimated_context_tokens(self) -> int:
        return self.context_budget().total_estimated_request_tokens

    def context_budget(self) -> ContextBudget:
        if not self.store.messages():
            return empty_context_budget(self.inference)
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
        request = self._model_request(
            capability_turn=self.agent_enabled,
            capability_names=(capabilities if self.agent_enabled else None),
        )
        return request.budget

    def _model_messages(
        self,
        *,
        capability_turn: bool | None = None,
        capability_names: tuple[str, ...] | None = None,
    ) -> list[dict]:
        return self._model_request(
            capability_turn=capability_turn,
            capability_names=capability_names,
        ).messages

    def _model_request(
        self,
        *,
        capability_turn: bool | None = None,
        capability_names: tuple[str, ...] | None = None,
    ) -> ContextSelection:
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
                - schema_reserve
                - DEFAULT_SAFETY_BUFFER_TOKENS,
            )
            if count_message_tokens(self.inference, [full_system]) >= budget:
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
            history = self.store.agent_messages(capability_names=())
        return select_context_request(
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
