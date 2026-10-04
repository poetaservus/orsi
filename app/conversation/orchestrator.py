from __future__ import annotations

import logging
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.agent.runtime import AgentRunStatus, AgentRuntime
from app.agent.contracts import AgentRunResult, SettledCall
from app.conversation.context import (
    ContextBudget,
    ContextSelection,
    calculate_context_budget,
    capability_schema_reserve,
    context_length,
    empty_context_budget,
    select_context_request,
)
from app.conversation.capability_routing import select_turn_capabilities
from app.conversation.prompt import (
    AGENT_CONVERSATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    compact_agent_system_prompt,
)
from app.conversation.result_grounding import grounded_text_read_answer
from app.conversation.store import ConversationStore, TurnHistoryError
from app.security.host_access import HostAccessPolicy, HostReadScope
from app.inference.engine import InferenceUnavailable
from app.inference.diagnostics import record_context_budget
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.runtime.skills import (
    SkillDefinition, SkillRegistry, SkillActivationError, SkillActivationErrorCode, with_active_skill,
    SkillCandidate, SkillSelection, select_skill,
)
from app.inference.completion import CompletionText, IncompleteResponseError
from app.runtime.skills.diagnostics import record_skill_event, skill_source


log = logging.getLogger(__name__)


class ConversationService:
    """UI-facing conversation session and the sole owner of agent turn lifecycle."""

    def _stored_agent_history(self, *, capability_names=None):
        return self.store.agent_messages(capability_names=self.agent_capabilities if capability_names is None else capability_names,
            openai_replay=getattr(self.inference, "supports_openai_replay", False) is True)

    def _retain_provider_response(self, scope, replay):
        try:
            self.store.record_response(self._active_turn_id, scope, replay)
        except Exception:
            self._history_persistence_failed = True
            raise TurnHistoryError("The model response could not be retained durably. Review this turn before retrying.") from None

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
        skill_registry: SkillRegistry | None = None,
        automatic_skills_enabled: bool = True,
    ):
        if type(automatic_skills_enabled) is not bool:
            raise TypeError("Automatic skill selection must be an explicit boolean.")
        if skill_registry is not None and not isinstance(skill_registry, SkillRegistry):
            raise TypeError("Conversation skills must use a SkillRegistry.")
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
        self.skill_registry = skill_registry if skill_registry is not None else SkillRegistry()
        self.automatic_skills_enabled = automatic_skills_enabled
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
        self._active_skill_name: str | None = None
        self._automatic_skill: SkillDefinition | None = None
        self.skill_selection = SkillSelection()
        self._turn_result: AgentRunResult | None = None
        self._history_persistence_failed = False
        # Measurements describe the latest physical request, never cumulative work.
        # Keep them scoped to this session/backend revision; legacy history has no
        # reliable model provenance and must use an explicitly labelled estimate.
        self._context_measurement = None
        if agent_runtime is not None:
            self.store.reconcile_journal(agent_runtime.executor.journal.records)
        self._agent_history = self._stored_agent_history()

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

    @property
    def active_skill(self) -> SkillDefinition | None:
        """Return the current explicit definition or this turn's automatic snapshot."""
        return self.skill_registry.get(self._active_skill_name) if self._active_skill_name is not None else deepcopy(self._automatic_skill)

    def activate_skill(self, name: str) -> SkillDefinition:
        """Explicitly select one catalog skill for this session, never during a turn."""
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Finish or stop the current response before changing skills.")
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
            return self._activate_skill_locked(name)
        finally:
            self._run_lock.release()

    def _activate_skill_locked(self, name: str) -> SkillDefinition:
        if not isinstance(name, str) or not name.strip():
            record_skill_event("activation_error", method="explicit", injected=False, error_code="invalid_name")
            raise SkillActivationError(SkillActivationErrorCode.INVALID_NAME,
                                       "Skill activation requires a non-empty string name.")
        skill = self.skill_registry.get(name)
        if skill is None:
            record_skill_event("activation_error", method="explicit", injected=False, error_code="missing_skill")
            raise SkillActivationError(SkillActivationErrorCode.MISSING_SKILL,
                                       "Requested skill is unavailable in the current catalog.")
        self._active_skill_name = skill.name
        self._automatic_skill = None
        self.skill_selection = SkillSelection(name=skill.name, reason="explicit")
        self._context_measurement = None
        self._record_skill_event("activated", skill=skill, method="explicit", injected=False)
        return skill

    def _record_skill_event(self, event: str, *, skill: SkillDefinition | None = None, **fields) -> None:
        record_skill_event(event, skill=skill,
            source=skill_source(skill, global_root=self.skill_registry.global_root,
                                project_root=self.skill_registry.project_root), **fields)

    def deactivate_skill(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Finish or stop the current response before changing skills.")
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
            self._record_skill_event("deactivated", skill=self.active_skill, injected=False)
            self._active_skill_name = None
            self._automatic_skill = None
            self.skill_selection = SkillSelection()
            self._context_measurement = None
        finally:
            self._run_lock.release()

    def install_skill(self, imported):
        """Publish a reviewed import and refresh the catalog only between turns."""
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Finish or stop the current response before installing skills.")
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
            from app.runtime.skills.import_source import install_import
            from app.runtime.skills.installer import SkillInstaller
            return install_import(SkillInstaller(self.skill_registry), imported)
        finally:
            self._run_lock.release()

    def remove_skill(self, name: str) -> None:
        """Remove a global skill between turns using existing removal safeguards."""
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Finish or stop the current response before removing skills.")
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
            from app.runtime.skills.installer import SkillInstaller
            effective = self.skill_registry.get(name)
            if effective is not None and not effective.source_path.is_relative_to(self.skill_registry.global_root):
                raise RuntimeError("Project skills must be managed in their project folder.")
            SkillInstaller(self.skill_registry).remove(name)
            removed_active = (self._active_skill_name == name or
                              self._automatic_skill is not None and self._automatic_skill.name == name)
            if self._active_skill_name == name:
                self._active_skill_name = None
            if self._automatic_skill is not None and self._automatic_skill.name == name:
                self._automatic_skill = None
            if removed_active:
                self.skill_selection = SkillSelection()
                self._context_measurement = None
        finally:
            self._run_lock.release()

    @property
    def supports_text_streaming(self):
        return getattr(self.inference, "supports_text_streaming", False) is True

    def run(self, user_message: str, activity=None, *, skill_name: str | None = None, text_observer=None) -> str:
        """Run one turn; an optional explicit skill applies only to this message."""
        text = str(user_message).strip()
        if not text:
            raise ValueError("Enter a message first.")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("O.R.S.I is already replying.")

        source = CancellationSource()
        turn_id = None
        previous_explicit_skill = self._active_skill_name
        previous_automatic_skill = self._automatic_skill
        message_skill = None
        preview_setter = getattr(self.inference, "set_text_observer", None)
        preview_attached = False
        cancellation_setter = getattr(self.inference, "set_request_cancellation", None)
        cancellation_attached = False
        try:
            with self._cancellation_lock:
                if self._closed:
                    raise RuntimeError("The conversation is closed.")
                self._cancellation = source
            if self.supports_text_streaming and callable(cancellation_setter):
                cancellation_setter(source.token)
                cancellation_attached = True
            if skill_name is not None:
                message_skill = self._activate_skill_locked(skill_name)
            # Local control commands are acknowledged without inference or durable
            # model history. '/skill' alone clears the current session selection.
            command = text.split(maxsplit=1)
            if command[0] == "/skill" and skill_name is None:
                if len(command) == 1:
                    self._record_skill_event("deactivated", skill=self.active_skill, injected=False)
                    self._active_skill_name = None
                    self._automatic_skill = None
                    self.skill_selection = SkillSelection()
                    self._context_measurement = None
                    return "Skill deactivated."
                skill = self._activate_skill_locked(command[1])
                label = skill.name if len(skill.name) <= 128 else skill.name[:125] + "..."
                return "Skill activated: " + json.dumps(label, ensure_ascii=True) + "."
            if self._history_persistence_failed:
                raise TurnHistoryError("A settled turn could not be retained safely. Review its outcomes before retrying.")
            turn_id = self.store.begin_turn(text)
            self._context_measurement = None
            self._active_turn_id = turn_id
            self._turn_result = None
            self._agent_history = self._stored_agent_history()
            self._automatic_skill = None
            self.skill_selection = SkillSelection()
            if self._active_skill_name is not None:
                self.skill_selection = SkillSelection(name=self._active_skill_name, reason="explicit")
            elif self.automatic_skills_enabled:
                candidates = tuple(SkillCandidate(skill.name, skill.description) for skill in self.skill_registry.list())
                if candidates and activity:
                    activity("Choosing a skill...")
                try:
                    self.skill_selection = select_skill(self.inference, candidates=candidates, request=text,
                                                       cancellation=source.token)
                except TaskCancelled:
                    record_skill_event("router", method="automatic", router_result="cancelled", injected=False)
                    raise
                self._record_skill_event("router", skill=self.skill_registry.get(self.skill_selection.name)
                    if self.skill_selection.name is not None else None, method="automatic",
                    router_result=self.skill_selection.reason, injected=False)
                if self.skill_selection.reason == "stop_failed":
                    raise RuntimeError("Skill selection could not stop its model request safely.")
                if self.skill_selection.name is not None:
                    selected = self.skill_registry.get(self.skill_selection.name)
                    if selected is not None and SkillCandidate(selected.name, selected.description) in candidates:
                        self._automatic_skill = selected
                    else:
                        self.skill_selection = replace(self.skill_selection, name=None, reason="catalog_changed")
                        record_skill_event("router", method="automatic", router_result="catalog_changed", injected=False)
            else:
                self.skill_selection = SkillSelection(reason="disabled")
                record_skill_event("router", method="none", router_result="disabled", injected=False)
            source.token.raise_if_cancelled()
            if text_observer is not None and callable(preview_setter):
                preview_setter(text_observer)
                preview_attached = True
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
            self._agent_history = self._stored_agent_history()
            return answer
        except Exception as exc:
            if turn_id is not None:
                outcome = self._turn_result
                if outcome is None or outcome.status == AgentRunStatus.COMPLETED:
                    prior_outcome = outcome
                    value = CompletionText(exc.partial_text or "", exc.completion, exc.completion_history) \
                        if isinstance(exc, IncompleteResponseError) else CompletionText("")
                    status = (AgentRunStatus.CANCELLED if isinstance(exc, TaskCancelled) or
                              isinstance(exc, IncompleteResponseError) and exc.completion.finish_reason == "cancelled" else
                              AgentRunStatus.INCOMPLETE if isinstance(exc, IncompleteResponseError) else
                              AgentRunStatus.MODEL_UNAVAILABLE if isinstance(exc, InferenceUnavailable) else
                              AgentRunStatus.CONTEXT_LIMIT if isinstance(exc, SkillActivationError)
                                  and exc.code == SkillActivationErrorCode.CONTEXT_LIMIT else
                              AgentRunStatus.INTERNAL_FAILURE)
                    outcome = AgentRunResult(status=status, message=str(exc).strip()[:500] or "The turn stopped.",
                        steps=prior_outcome.steps if prior_outcome else 0,
                        capability_calls=prior_outcome.capability_calls if prior_outcome else 0,
                        protocol_failures=prior_outcome.protocol_failures if prior_outcome else 0,
                        model_requests=prior_outcome.model_requests if prior_outcome else 0,
                        consecutive_format_failures=prior_outcome.consecutive_format_failures if prior_outcome else 0,
                        semantic_corrections=prior_outcome.semantic_corrections if prior_outcome else 0,
                        inference_requests=prior_outcome.inference_requests if prior_outcome else 0,
                        estimated_input_tokens=prior_outcome.estimated_input_tokens if prior_outcome else 0,
                        context_projections=prior_outcome.context_projections if prior_outcome else 0,
                        context_compactions=prior_outcome.context_compactions if prior_outcome else 0,
                        completion=prior_outcome.completion if prior_outcome else value.completion,
                        completion_history=prior_outcome.completion_history if prior_outcome else value.completion_history,
                        partial_text=prior_outcome.assistant_text if prior_outcome else str(value) or None,
                        settled_calls=prior_outcome.settled_calls if prior_outcome else ())
                try:
                    self.store.finish_turn(turn_id, outcome, outcome.partial_text)
                    self._agent_history = self._stored_agent_history()
                except Exception:
                    self._history_persistence_failed = True
                    self._agent_history.append({"role": "assistant", "content":
                        f"Turn stopped ({outcome.status.value}). {outcome.message or 'History persistence failed.'}"})
                    log.exception("Stopped turn outcomes could not be persisted.")
                if isinstance(exc, TurnHistoryError):
                    self._history_persistence_failed = True
                self._turn_result = outcome
            if isinstance(exc, TaskCancelled):
                return "The response was stopped."
            raise
        finally:
            if cancellation_attached:
                cancellation_setter(None)
            if preview_attached:
                preview_setter(None)
            if turn_id is not None and self._turn_result is not None:
                usage = self._turn_result.completion.usage
                used = usage.total_tokens
                if used is None and usage.input_tokens is not None and usage.output_tokens is not None:
                    used = usage.input_tokens + usage.output_tokens
                if used is not None:
                    self._context_measurement = (self._context_measurement_key(), used)
            with self._cancellation_lock:
                if self._cancellation is source:
                    self._cancellation = None
            if skill_name is not None:
                self._active_skill_name = previous_explicit_skill
                self._automatic_skill = None if message_skill is not None else previous_automatic_skill
                if message_skill is not None:
                    self._record_skill_event("deactivated", skill=message_skill, method="explicit", injected=False)
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
        self._record_skill_injection(request)
        response = self.inference.respond(request.messages)
        source.token.raise_if_cancelled()
        if isinstance(response, str) and getattr(response, "completion", None) is not None:
            if response.completion.incomplete and not response.strip():
                raise IncompleteResponseError("The response was cut off.", response.completion,
                                              history=response.completion_history)
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("The model returned an empty response.")
        text = CompletionText(response)
        if text.openai_response is not None and not text.completion.incomplete:
            self._retain_provider_response(uuid4().hex, text.openai_response)
        return CompletionText(str(text) if text.completion.incomplete else text.strip(),
                              text.completion, text.completion_history, openai_response=text.openai_response)

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
            self._turn_result = AgentRunResult(status=AgentRunStatus.CONTEXT_LIMIT,
                message="The current requirements and capability catalog cannot fit the active model context window.",
                steps=0, capability_calls=0, protocol_failures=0)
            raise RuntimeError("The agent request cannot fit the active model context window.")
        self._record_skill_injection(request)
        result = self.agent_runtime.run(
            request.messages,
            session_id=self._session_id,
            turn_id=self._active_turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            settled_observer=retain_settled,
            response_observer=self._retain_provider_response,
            capability_names=capabilities,
        )
        self._turn_result = result
        if result.status == AgentRunStatus.CANCELLED:
            if result.partial_text:
                raise IncompleteResponseError("The response was stopped.", result.completion,
                    result.partial_text, result.completion_history)
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
        cancel = getattr(self.inference, "cancel_current_request", None)
        if callable(cancel):
            cancel()
        return True

    def new_session(self, *, preserve_history: bool = False) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Stop the current response before starting a new session.")
        try:
            self.store.new_session(preserve_history=preserve_history)
            if self.active_skill is not None:
                self._record_skill_event("deactivated", skill=self.active_skill, injected=False)
            self._session_id = self.store.session_id
            self._history_persistence_failed = False
            self._agent_history = []
            self._active_skill_name = None
            self._automatic_skill = None
            self.skill_selection = SkillSelection()
            self._context_measurement = None
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

    def _context_measurement_key(self) -> tuple:
        return (self.store.session_id, id(self.inference),
                getattr(self.inference, "context_revision", 0),
                getattr(self.inference, "mode", None), context_length(self.inference))

    def reported_context_tokens(self) -> int | None:
        """Latest reported request occupancy, or unknown after session/model changes."""
        measurement = self._context_measurement
        if measurement is None or measurement[0] != self._context_measurement_key():
            return None
        return measurement[1]

    def context_budget(self) -> ContextBudget:
        if not self.store.messages() and self._active_skill_name is None and self._automatic_skill is None:
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
            prompt = compact_agent_system_prompt(
                self.host_read_scope or HostReadScope.PORTABLE_ROOT,
                capabilities,
                user_home=(
                    str(self.host_access_policy.user_home)
                    if self.host_access_policy is not None
                    else None
                ),
            )
            # Native tool descriptions/schemas already carry per-tool contracts.
            # Keep one shared policy prompt at every context size, rather than
            # repeating the complete catalog as prose until space runs out.
            history = self._agent_history
        else:
            prompt = AGENT_CONVERSATION_SYSTEM_PROMPT if self.agent_enabled else SYSTEM_PROMPT
            history = self._stored_agent_history(capability_names=())
        skill = self.active_skill
        if self._active_skill_name is not None and skill is None:
            record_skill_event("activation_error", method="explicit", injected=False, error_code="missing_skill")
            raise SkillActivationError(SkillActivationErrorCode.MISSING_SKILL,
                                       "Active skill is unavailable. Select another skill or use /skill to clear it.")
        core_prompt = prompt
        prompt = with_active_skill(core_prompt, skill)
        if skill is not None:
            latest_user = next((message for message in reversed(history) if message.get("role") == "user"), None)
            # Added guidance must not displace or truncate the current user task.
            required = [{"role": "system", "content": prompt}]
            if latest_user is not None:
                required.append(latest_user)
            if not calculate_context_budget(self.inference, required, reserved_tokens=schema_reserve).fits:
                self._record_skill_event("rejected", skill=skill,
                    method="explicit" if self._active_skill_name is not None else "automatic",
                    router_result="skill_context_limit", injected=False, error_code="context_limit")
                if self._active_skill_name is not None:
                    raise SkillActivationError(SkillActivationErrorCode.CONTEXT_LIMIT,
                                               "The active skill and current task cannot fit the model context. Use /skill to clear it.")
                # Optional automatic guidance cannot make an otherwise admissible
                # task fail. Explicit activation retains its Phase 3.1 contract.
                self._automatic_skill = None
                self.skill_selection = replace(self.skill_selection, name=None, reason="skill_context_limit")
                prompt = core_prompt
        return select_context_request(
            self.inference,
            system_prompt=prompt,
            history=history,
            reserved_tokens=schema_reserve,
            recovery_enabled=bool(self.agent_runtime and self.agent_runtime.context_recovery_enabled),
        )

    def _record_skill_injection(self, request: ContextSelection) -> None:
        """Record only admitted answer inputs, never context-meter projections."""
        system = request.messages[0]["content"]
        if "\nACTIVE SKILL\n" not in system:
            return
        # Use the rendered snapshot: a concurrent reload may replace or remove
        # the catalog definition after the request is constructed.
        payload = json.loads(system.rsplit("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0])
        skill = self.skill_registry.get(payload["name"])
        if skill is not None and skill.instructions != payload["instructions"]:
            skill = None
        record_skill_event("injected", name=payload["name"], instructions=payload["instructions"],
            source=skill_source(skill, global_root=self.skill_registry.global_root,
                                project_root=self.skill_registry.project_root),
            method="explicit" if self._active_skill_name is not None else "automatic",
            router_result=self.skill_selection.reason, injected=True,
            system_message_tokens=request.budget.system_message_tokens)

    def _planner_capabilities(self) -> tuple[str, ...]:
        """Return the full registry catalog without applying semantic routing."""
        return self.agent_capabilities

    def _turn_capabilities(self, latest_user_text: str) -> tuple[str, ...]:
        """Resolve visibility from the enabled registry, never from task wording.

        Permissions and approvals still authorize each concrete invocation in
        the runtime. Context recovery only controls context management.
        """
        if self.agent_runtime is None:
            return ()
        return select_turn_capabilities(latest_user_text, self.agent_capabilities)

    def _capability_schema_reserve(self, names: tuple[str, ...]) -> int:
        if self.agent_runtime is None or not names:
            return 0
        selected = set(names)
        definitions = tuple(
            definition
            for definition in self.agent_runtime.registry.model_definitions()
            if definition.name in selected
        )
        return capability_schema_reserve(definitions, inference=self.inference)
