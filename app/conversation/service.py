from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4

from app.agent_runtime import AgentRunStatus, AgentRuntime
from app.conversation.prompt import (
    AGENT_CONVERSATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    agent_system_prompt,
)
from app.conversation.store import ConversationStore
from app.host_access import HostAccessPolicy, HostReadScope
from app.inference.protocol import (
    ModelCapabilityCall,
    model_capability_calls_message,
    model_capability_result_message,
)
from app.runtime.cancellation import CancellationSource, TaskCancelled


@dataclass(slots=True)
class _ActiveDirectoryListing:
    path: str
    files: tuple[str, ...]
    metadata_received: set[str] = field(default_factory=set)


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
            host_access_policy, HostAccessPolicy
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
        self._active_listing: _ActiveDirectoryListing | None = None
        self._last_filesystem_operation: str | None = None
        self._awaiting_folder_path = False
        # Capability calls/results stay only in memory for coherent follow-ups.
        # ConversationStore intentionally persists user and final assistant text only.
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
            if self.agent_enabled:
                self._agent_history.append({"role": "user", "content": text})
            folder_request = text
            if self._awaiting_folder_path and _folder_creation_target(f"mkdir {text}"):
                folder_request = f"mkdir {text}"
            self._awaiting_folder_path = False
            if _is_folder_creation_request(folder_request):
                answer = self._create_folder(folder_request, source, activity)
                self.store.append("assistant", answer)
                if self.agent_enabled:
                    self._agent_history.append({"role": "assistant", "content": answer})
                return answer
            if _is_text_write_request(text):
                answer = self._write_text(text, source, activity)
                self.store.append("assistant", answer)
                if self.agent_enabled:
                    self._agent_history.append({"role": "assistant", "content": answer})
                return answer
            if _is_copy_request(text):
                answer = self._copy_file(text, source, activity)
                self.store.append("assistant", answer)
                if self.agent_enabled:
                    self._agent_history.append({"role": "assistant", "content": answer})
                return answer
            if _is_move_request(text):
                answer = self._move_file(text, source, activity)
                self.store.append("assistant", answer)
                if self.agent_enabled:
                    self._agent_history.append({"role": "assistant", "content": answer})
                return answer
            if _is_trash_request(text):
                answer = self._trash_file(text, source, activity)
                self.store.append("assistant", answer)
                if self.agent_enabled:
                    self._agent_history.append({"role": "assistant", "content": answer})
                return answer
            capability_turn = self.agent_enabled and self._requires_capabilities(text)
            if activity:
                activity("Working..." if capability_turn else "Thinking...")
            source.token.raise_if_cancelled()
            if self.agent_runtime is None:
                response = self.inference.respond(self._model_messages())
                source.token.raise_if_cancelled()
                if not isinstance(response, str) or not response.strip():
                    raise RuntimeError("The model returned an empty response.")
                answer = response.strip()
            else:
                self._turn_number += 1
                turn_id = f"turn-{self._turn_number}"
                turn_trace: list[dict] = []
                turn_results: list[tuple] = []
                required_calls: tuple[ModelCapabilityCall, ...] = ()
                if capability_turn:
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
                        self._retain_filesystem_context(calls, results)

                    required_calls = self._required_capability_calls(text)
                    result = self.agent_runtime.run(
                        self._model_messages(capability_turn=True),
                        session_id=self._session_id,
                        turn_id=turn_id,
                        portable_root=self.portable_root,
                        allowed_read_roots=self.allowed_read_roots,
                        host_access_policy=self.host_access_policy,
                        cancellation=source.token,
                        result_observer=retain_results,
                        required_calls=required_calls,
                        capability_names=self._read_capabilities(),
                    )
                else:
                    result = self.agent_runtime.run_conversation(
                        self._model_messages(capability_turn=False),
                        cancellation=source.token,
                    )
                if result.status == AgentRunStatus.CANCELLED:
                    return "The response was stopped."
                if result.status != AgentRunStatus.COMPLETED:
                    raise RuntimeError(
                        result.message or "The bounded agent run did not complete."
                    )
                answer = result.assistant_text.strip()
                if required_calls and all(
                    call.capability == "filesystem.stat" for call in required_calls
                ):
                    answer = _render_metadata_results(required_calls, turn_results)
                elif required_calls and all(
                    call.capability == "filesystem.find" for call in required_calls
                ):
                    answer = _render_find_result(required_calls, turn_results)
                elif required_calls and all(
                    call.capability == "filesystem.list" for call in required_calls
                ):
                    answer = _render_listing_results(required_calls, turn_results)
                elif required_calls and all(
                    call.capability == "filesystem.read_text" for call in required_calls
                ):
                    answer = _render_text_result(required_calls, turn_results)
                elif required_calls and all(
                    call.capability == "filesystem.search" for call in required_calls
                ):
                    answer = _render_search_result(required_calls, turn_results)
                completed_capabilities = {
                    call.capability for call, _result in turn_results
                }
                if "filesystem.find" in completed_capabilities:
                    self._last_filesystem_operation = "find"
                elif "filesystem.search" in completed_capabilities:
                    self._last_filesystem_operation = "search"
                elif "filesystem.read_text" in completed_capabilities:
                    self._last_filesystem_operation = "read_text"
                elif "filesystem.stat" in completed_capabilities:
                    self._last_filesystem_operation = "metadata"
                elif "filesystem.list" in completed_capabilities:
                    self._last_filesystem_operation = "listing"
                else:
                    self._last_filesystem_operation = None
            self.store.append("assistant", answer)
            if self.agent_enabled:
                if capability_turn:
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

    def _read_capabilities(self) -> tuple[str, ...]:
        return tuple(
            name for name in self.agent_capabilities
            if name not in {"filesystem.mkdir", "filesystem.write_text", "filesystem.copy", "filesystem.move", "filesystem.trash"}
        )

    def _create_folder(self, text, source, activity) -> str:
        self._last_filesystem_operation = None
        if "filesystem.mkdir" not in self.agent_capabilities:
            return "Folder creation is not enabled. No folder was created."
        target = _folder_creation_target(text)
        if target is None:
            self._awaiting_folder_path = True
            return "What is the full absolute path of the new folder? Its parent folder must already exist."
        self._turn_number += 1
        call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-1",
            capability="filesystem.mkdir", arguments={"path": target},
        )
        observed = []
        if activity:
            activity("Preparing folder approval...")
        result = self.agent_runtime.run(
            [{"role": "user", "content": text}],
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=("filesystem.mkdir",),
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "Folder creation was cancelled before execution."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "Folder creation did not complete.")
        if not observed:
            raise RuntimeError("The folder creation result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            return outcome.error.message if outcome.error else "The folder could not be created."
        self._active_listing = None
        return f"Created empty folder: {outcome.output['path']}"

    def _write_text(self, text, source, activity) -> str:
        self._last_filesystem_operation = None
        if "filesystem.write_text" not in self.agent_capabilities:
            return "Text-file writing is not enabled. No file was changed."
        request = _text_write_request(text)
        if request is None:
            return "Tell me the exact file path and text to write, for example: write text to C:\\Users\\you\\Desktop\\note.txt:\nHello"
        target, content = request
        self._turn_number += 1
        call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-1",
            capability="filesystem.write_text", arguments={"path": target, "text": content},
        )
        observed = []
        if activity:
            activity("Preparing file approval...")
        result = self.agent_runtime.run(
            [{"role": "user", "content": text}],
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=("filesystem.write_text",),
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "Text-file writing was cancelled before execution."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "Text-file writing did not complete.")
        if not observed:
            raise RuntimeError("The text-file write result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            return outcome.error.message if outcome.error else "The text file could not be written."
        self._active_listing = None
        output = outcome.output or {}
        return f"Wrote text file: {output['path']} ({output['bytes_written']:,} bytes, {output['operation']})."

    def _copy_file(self, text, source, activity) -> str:
        self._last_filesystem_operation = None
        if "filesystem.copy" not in self.agent_capabilities:
            return "File copying is not enabled. No file was changed."
        request = _copy_request(text)
        if request is None:
            return "Tell me the exact source and destination paths, for example: copy C:\\Users\\you\\Desktop\\a.txt to C:\\Users\\you\\Desktop\\b.txt"
        source_path, destination_path, on_collision = request
        self._turn_number += 1
        call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-1",
            capability="filesystem.copy",
            arguments={"source_path": source_path, "destination_path": destination_path,
                       "on_collision": on_collision},
        )
        observed = []
        if activity:
            activity("Preparing copy approval...")
        result = self.agent_runtime.run(
            [{"role": "user", "content": text}],
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=("filesystem.copy",),
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "File copying was cancelled before execution."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "File copying did not complete.")
        if not observed:
            raise RuntimeError("The file-copy result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            return outcome.error.message if outcome.error else "The file could not be copied."
        self._active_listing = None
        output = outcome.output or {}
        return (f"Copied file: {output['destination_path']} "
                f"({output['bytes_copied']:,} bytes, {output['operation']}).")

    def _move_file(self, text, source, activity) -> str:
        self._last_filesystem_operation = None
        if "filesystem.move" not in self.agent_capabilities:
            return "File moving is not enabled. No file was changed."
        request = _move_request(text)
        if request is None:
            return "Tell me the exact source and destination paths, for example: move C:\\Users\\you\\Desktop\\a.txt to C:\\Users\\you\\Desktop\\b.txt"
        source_path, destination_path, on_collision = request
        self._turn_number += 1
        call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-1",
            capability="filesystem.move",
            arguments={"source_path": source_path, "destination_path": destination_path,
                       "on_collision": on_collision},
        )
        observed = []
        if activity:
            activity("Preparing move approval...")
        result = self.agent_runtime.run(
            [{"role": "user", "content": text}],
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=("filesystem.move",),
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "File moving was cancelled before execution."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "File moving did not complete.")
        if not observed:
            raise RuntimeError("The file-move result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            return outcome.error.message if outcome.error else "The file could not be moved."
        self._active_listing = None
        output = outcome.output or {}
        return (f"Moved file: {output['destination_path']} "
                f"({output['bytes_moved']:,} bytes, {output['operation']}).")

    def _trash_file(self, text, source, activity) -> str:
        self._last_filesystem_operation = None
        if "filesystem.trash" not in self.agent_capabilities:
            return "File trashing is not enabled. No file was changed."
        target = _trash_target(text)
        if target is None:
            return "Tell me the exact file path to send to the Recycle Bin, for example: trash C:\\Users\\you\\Desktop\\old.txt"
        self._turn_number += 1
        call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-1",
            capability="filesystem.trash", arguments={"path": target},
        )
        observed = []
        if activity:
            activity("Preparing trash approval...")
        result = self.agent_runtime.run(
            [{"role": "user", "content": text}],
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=("filesystem.trash",),
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "File trashing was cancelled before execution."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "File trashing did not complete.")
        if not observed:
            raise RuntimeError("The file-trash result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            return outcome.error.message if outcome.error else "The file could not be sent to the Recycle Bin."
        self._active_listing = None
        output = outcome.output or {}
        return f"Sent file to Recycle Bin: {output['path']} ({output['bytes_trashed']:,} bytes)."

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
            self._active_listing = None
            self._last_filesystem_operation = None
            self._awaiting_folder_path = False
            self._agent_history = []
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

    def _model_messages(
        self,
        *,
        capability_turn: bool | None = None,
    ) -> list[dict]:
        prompt = (
            (
                agent_system_prompt(
                    self.host_read_scope or HostReadScope.PORTABLE_ROOT,
                    self._read_capabilities(),
                )
                if capability_turn is not False
                else AGENT_CONVERSATION_SYSTEM_PROMPT
            )
            if self.agent_enabled
            else SYSTEM_PROMPT
        )
        system = {"role": "system", "content": prompt}
        # Token counting may lazily load the local model and replace the
        # startup context hint with the context it could actually allocate.
        self._count_tokens([system])
        prompt_budget = max(1, self._context_length() - self._response_reserve())
        history = (
            self._agent_history
            if self.agent_enabled and capability_turn is not False
            else self.store.messages()
        )
        selected: list[dict] = []
        for group in reversed(_conversation_turn_groups(history)):
            candidate_group = deepcopy(group)
            candidate = [system, *candidate_group, *selected]
            if self._count_tokens(candidate) <= prompt_budget:
                selected[0:0] = candidate_group
                continue

            truncated = None
            if (
                len(candidate_group) == 1
                and set(candidate_group[0]) == {"role", "content"}
                and isinstance(candidate_group[0].get("content"), str)
            ):
                truncated = self._largest_fitting_suffix(
                    system,
                    candidate_group[0],
                    selected,
                    prompt_budget,
                )
            if truncated is not None:
                selected.insert(0, truncated)
            break
        return [system, *selected]

    def _requires_capabilities(self, text: str) -> bool:
        available = set(self.agent_capabilities)
        lowered = " ".join(str(text).casefold().split())
        if not lowered or not available:
            return False
        if "filesystem.stat" in available and re.search(
            r"\bfilesystem[.]stat\b", lowered
        ):
            return True
        if "filesystem.find" in available and re.search(
            r"\bfilesystem[.]find\b", lowered
        ):
            return True
        if "filesystem.list" in available and re.search(
            r"\bfilesystem[.]list\b", lowered
        ):
            return True
        if "filesystem.read_text" in available and re.search(
            r"\bfilesystem[.]read_text\b", lowered
        ):
            return True
        if "filesystem.search" in available and re.search(
            r"\bfilesystem[.]search\b", lowered
        ):
            return True

        filesystem_object = re.search(
            r"\b(?:files?|folders?|directories|directory|paths?|drives?|entries|contents)\b",
            lowered,
        )
        path_like = re.search(
            r"(?:\b[a-z]:[\\/]|\\\\|\b[^\\/\s]+[.][a-z0-9]{1,12}\b)",
            lowered,
        )
        if (
            "filesystem.find" in available
            and _find_target(text, self.host_access_policy) is not None
        ):
            return True
        if (
            "filesystem.read_text" in available
            and _is_text_read_request(lowered)
            and (self._text_read_target(text) is not None or path_like is not None)
        ):
            return True
        if (
            "filesystem.search" in available
            and _is_search_request(lowered)
            and (_search_target_and_query(text) is not None or path_like is not None)
        ):
            return True
        if "filesystem.stat" in available:
            if self._metadata_continuation_targets(text):
                return True
            if re.search(r"\b(?:metadata|file properties|directory properties)\b", lowered):
                return True
            if re.search(
                r"\b(?:size|bytes?|created|creation|modified|modification|timestamps?|stat)\b",
                lowered,
            ) and (filesystem_object or path_like):
                return True
            if re.search(r"\b(?:inspect|check)\b.{0,80}\b(?:file|folder|directory|path)\b", lowered):
                return True

        if "filesystem.list" in available:
            if _explicit_windows_path(text) is not None and _is_listing_request(lowered):
                return True
            if re.search(
                r"\b(?:list|show|display)\b.{0,80}\b"
                r"(?:files?|folders?|director(?:y|ies)|entries|contents|items)\b",
                lowered,
            ):
                return True
            if re.search(r"\b(?:what|which)\s+(?:files?|folders?|directories|entries|items)\b", lowered):
                return True
            if re.search(
                r"\b(?:files?|folders?|directories|entries|items)\s+"
                r"(?:do\s+i\s+have|are\s+(?:in|inside|under|there))\b",
                lowered,
            ):
                return True
            if re.search(r"\b(?:contents|entries)\s+(?:of|in|inside)\b", lowered):
                return True
            if self._active_listing is not None and re.search(
                r"\b(?:next|another|more)\s+(?:page|entries|files|results)\b",
                lowered,
            ):
                return True
        return False

    def _required_capability_calls(
        self,
        text: str,
    ) -> tuple[ModelCapabilityCall, ...]:
        listing = self._active_listing
        lowered = " ".join(str(text).casefold().split())
        find_target = _find_target(text, self.host_access_policy)
        if (
            find_target is not None
            and _is_listing_request(lowered)
            and find_target[2] == "directory"
            and "filesystem.list" in self.agent_capabilities
        ):
            find_path, name, _kind = find_target
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.list",
                    arguments={"path": str(Path(find_path) / name)},
                ),
            )
        if (
            find_target is not None
            and "filesystem.find" in self.agent_capabilities
        ):
            find_path, name, kind = find_target
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.find",
                    arguments={"path": find_path, "name": name, "kind": kind},
                ),
            )
        search_target = _search_target_and_query(text)
        if (
            search_target is not None
            and "filesystem.search" in self.agent_capabilities
        ):
            search_path, query = search_target
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.search",
                    arguments={"path": search_path, "query": query},
                ),
            )
        read_text_target = self._text_read_target(text)
        if (
            read_text_target is not None
            and "filesystem.read_text" in self.agent_capabilities
        ):
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.read_text",
                    arguments={"path": read_text_target},
                ),
            )
        metadata_request = re.search(
            r"\b(?:metadata|file properties|directory properties|size|bytes?|created|creation|"
            r"modified|modification|timestamps?|stat)\b",
            lowered,
        )
        continuation_targets = self._metadata_continuation_targets(text)
        if (
            listing is not None
            and "filesystem.stat" in self.agent_capabilities
            and (metadata_request or continuation_targets)
        ):
            if continuation_targets:
                targets = list(continuation_targets)
            elif re.search(r"\b(?:the\s+)?(?:rest|remaining)\b", lowered):
                targets = [
                    name for name in listing.files if name not in listing.metadata_received
                ]
            elif re.search(r"\b(?:each|every|all)(?:\s+of\s+the)?\s+files?\b", lowered):
                targets = list(listing.files)
            else:
                targets = [
                    name for name in listing.files if _mentions_filename(lowered, name)
                ]
            if targets and len(targets) <= 7:
                return tuple(
                    ModelCapabilityCall(
                        provider_call_id=f"required-{self._turn_number}-{index}",
                        capability="filesystem.stat",
                        arguments={"path": str(Path(listing.path) / name)},
                    )
                    for index, name in enumerate(targets, start=1)
                )

        requested_path = _explicit_windows_path(text)
        if (
            requested_path is not None
            and "filesystem.list" in self.agent_capabilities
            and _is_listing_request(lowered)
        ):
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.list",
                    arguments={"path": requested_path},
                ),
            )
        return ()

    def _text_read_target(self, text: str) -> str | None:
        if (
            "filesystem.read_text" not in self.agent_capabilities
            or not _is_text_read_request(" ".join(str(text).casefold().split()))
        ):
            return None
        requested_path = _explicit_windows_path(text)
        if requested_path is not None:
            return requested_path
        listing = self._active_listing
        if listing is None:
            return None
        lowered = " ".join(str(text).casefold().split())
        exact_matches = [
            name for name in listing.files if _mentions_filename(lowered, name)
        ]
        if len(exact_matches) == 1:
            return str(Path(listing.path) / exact_matches[0])
        stem_matches = [
            name for name in listing.files if _mentions_filename(lowered, Path(name).stem)
        ]
        if len(stem_matches) == 1:
            return str(Path(listing.path) / stem_matches[0])
        return None

    def _metadata_continuation_targets(self, text: str) -> tuple[str, ...]:
        listing = self._active_listing
        if listing is None or self._last_filesystem_operation != "metadata":
            return ()
        lowered = " ".join(str(text).casefold().split())
        if re.search(
            r"^(?:and\s+)?for\b|^what\s+about\b|\b(?:as\s+well|also|too|same\s+for)\b",
            lowered,
        ) is None:
            return ()
        return tuple(
            name for name in listing.files if _mentions_filename(lowered, name)
        )

    def _retain_filesystem_context(self, calls, results) -> None:
        for call, result in zip(calls, results, strict=True):
            if not result.success or not isinstance(result.output, dict):
                continue
            output = result.output
            if call.capability == "filesystem.list":
                path = output.get("path")
                entries = output.get("entries")
                if not isinstance(path, str) or not isinstance(entries, list):
                    continue
                files = tuple(
                    entry["name"]
                    for entry in entries
                    if isinstance(entry, dict)
                    and isinstance(entry.get("name"), str)
                    and entry.get("type") == "file"
                )
                cursor = call.arguments.get("cursor")
                if (
                    cursor is not None
                    and self._active_listing is not None
                    and _same_path(self._active_listing.path, path)
                ):
                    combined = tuple(dict.fromkeys((*self._active_listing.files, *files)))
                    self._active_listing.files = combined
                else:
                    self._active_listing = _ActiveDirectoryListing(path=path, files=files)
                continue
            if call.capability != "filesystem.stat" or self._active_listing is None:
                continue
            path = output.get("path")
            if not isinstance(path, str):
                continue
            candidate = Path(path)
            if not _same_path(str(candidate.parent), self._active_listing.path):
                continue
            for name in self._active_listing.files:
                if name.casefold() == candidate.name.casefold():
                    self._active_listing.metadata_received.add(name)
                    break

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

    def _count_tokens(self, messages: list[dict]) -> int:
        counter = getattr(self.inference, "count_message_tokens", None)
        countable = [
            message
            if set(message) == {"role", "content"}
            and isinstance(message.get("content"), str)
            else {
                "role": str(message.get("role", "assistant")),
                "content": json.dumps(
                    message,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
            for message in messages
        ]
        if callable(counter):
            return max(1, int(counter(countable)))
        characters = sum(len(message["content"]) for message in countable)
        return max(1, (characters + 3) // 4 + 4 * len(countable) + 3)

    def _context_length(self) -> int:
        return max(512, int(getattr(self.inference, "context_length", 8192)))

    def _response_reserve(self) -> int:
        configured = max(32, int(getattr(self.inference, "max_response_tokens", 512)))
        return min(configured, self._context_length() // 2)


_FOLDER_REQUEST = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:(?:create|make)\s+(?:(?:a|an|new|empty)\s+)*(?:folder|directory)\b"
    r"|(?:filesystem[.]mkdir|mkdir)\b)", re.I,
)


def _is_folder_creation_request(text: str) -> bool:
    return _FOLDER_REQUEST.match(text.strip()) is not None


def _folder_creation_target(text: str) -> str | None:
    match = _FOLDER_REQUEST.match(text.strip())
    if match is None:
        return None
    remainder = text.strip()[match.end():].strip()
    remainder = re.sub(r"^(?:at path|at)\s+", "", remainder, flags=re.I)
    if remainder.startswith(('"', "'")):
        quote = remainder[0]
        if len(remainder) < 3 or remainder[-1] != quote:
            return None
        remainder = remainder[1:-1]
    if (not re.fullmatch(r"[A-Za-z]:[\\/].+", remainder)
            or re.search(r"[\r\n\"']|\s+(?:and|then)\s+", remainder, re.I)
            or len(re.findall(r"[A-Za-z]:[\\/]", remainder)) != 1):
        return None
    return remainder


_TEXT_WRITE_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:(?:write|save)\b|filesystem[.]write_text\b)", re.I,
)


def _is_text_write_request(text: str) -> bool:
    value = str(text).strip()
    lowered = " ".join(value.casefold().split())
    if re.match(r"\Afilesystem[.]write_text\b", lowered):
        return True
    if _TEXT_WRITE_START.match(value) is None:
        return False
    return (
        _text_write_request(value) is not None
        or (re.search(r"\bto\b", lowered) is not None
            and re.search(r"[A-Za-z]:[\\/]", value) is not None)
    )


def _text_write_request(text: str) -> tuple[str, str] | None:
    value = str(text).strip()
    first_line, separator, content = value.partition("\n")
    if separator:
        match = re.match(
            r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:write|save)\s+"
            r"(?:(?:the|this|following|exact)\s+)?(?:text|content|file)\s+to\s+(.+):\s*\Z",
            first_line.strip(), re.I,
        )
        if match is not None:
            path = _write_path_argument(match.group(1))
            if path is not None:
                return path, content
    match = re.match(
        r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:write|save)\s+"
        r"(?:(?:text|content)\s+)?(?P<quote>[\"'])(?P<content>.*)(?P=quote)\s+to\s+(?P<path>.+)\Z",
        value, re.I | re.S,
    )
    if match is not None:
        path = _write_path_argument(match.group("path"))
        if path is not None:
            return path, match.group("content")
    match = re.match(
        r"\Afilesystem[.]write_text\s+(?P<path>(?:\"[^\"]+\"|'[^']+'|[A-Za-z]:[^\r\n]+?))\s+"
        r"(?P<quote>[\"'])(?P<content>.*)(?P=quote)\Z",
        value, re.I | re.S,
    )
    if match is not None:
        path = _write_path_argument(match.group("path"))
        if path is not None:
            return path, match.group("content")
    return None


def _write_path_argument(raw: str) -> str | None:
    value = str(raw).strip()
    if value.startswith(("\"", "'")):
        quote = value[0]
        if len(value) < 3 or value[-1] != quote:
            return None
        value = value[1:-1]
    if (not re.fullmatch(r"[A-Za-z]:[\\/].+", value)
            or re.search(r"[\r\n\"']|\s+(?:and|then)\s+", value, re.I)
            or len(re.findall(r"[A-Za-z]:[\\/]", value)) != 1):
        return None
    return value


_COPY_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:filesystem[.]copy|copy)\b",
    re.I,
)


def _is_copy_request(text: str) -> bool:
    return _COPY_START.match(str(text).strip()) is not None


def _copy_request(text: str) -> tuple[str, str, str] | None:
    value = str(text).strip()
    match = _COPY_START.match(value)
    if match is None:
        return None
    remainder = value[match.end():].strip()
    remainder = re.sub(r"^(?:file\s+)?(?:from\s+)?", "", remainder, flags=re.I)
    parts = re.split(r"\s+to\s+", remainder, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None
    source = _write_path_argument(parts[0])
    destination_text = parts[1].strip()
    on_collision = "fail"
    policy = re.search(
        r"\s+(?:(?:with\s+)?(?:replace|overwrite)(?:\s+existing(?:\s+file)?)?|replacing\s+existing(?:\s+file)?)\s*\Z",
        destination_text, re.I,
    )
    if policy is not None:
        on_collision = "replace"
        destination_text = destination_text[:policy.start()].strip()
    destination = _write_path_argument(destination_text)
    if source is None or destination is None:
        return None
    return source, destination, on_collision


_MOVE_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:filesystem[.]move|move)\b",
    re.I,
)


def _is_move_request(text: str) -> bool:
    value = str(text).strip()
    if _MOVE_START.match(value) is None:
        return False
    return (
        _move_request(value) is not None
        or (re.search(r"\s+to\s+", value, re.I) is not None
            and re.search(r"[A-Za-z]:[\\/]", value) is not None)
    )


def _move_request(text: str) -> tuple[str, str, str] | None:
    value = str(text).strip()
    match = _MOVE_START.match(value)
    if match is None:
        return None
    remainder = value[match.end():].strip()
    remainder = re.sub(r"^(?:file\s+)?(?:from\s+)?", "", remainder, flags=re.I)
    parts = re.split(r"\s+to\s+", remainder, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None
    source = _write_path_argument(parts[0])
    destination_text = parts[1].strip()
    on_collision = "fail"
    policy = re.search(
        r"\s+(?:(?:with\s+)?(?:replace|overwrite)(?:\s+existing(?:\s+file)?)?|replacing\s+existing(?:\s+file)?)\s*\Z",
        destination_text, re.I,
    )
    if policy is not None:
        on_collision = "replace"
        destination_text = destination_text[:policy.start()].strip()
    destination = _write_path_argument(destination_text)
    if source is None or destination is None:
        return None
    return source, destination, on_collision


_TRASH_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:filesystem[.]trash|trash|recycle|delete)\b",
    re.I,
)


def _is_trash_request(text: str) -> bool:
    value = str(text).strip()
    if _TRASH_START.match(value) is None:
        return False
    return _trash_target(value) is not None or re.search(r"[A-Za-z]:[\\/]", value) is not None


def _trash_target(text: str) -> str | None:
    value = str(text).strip()
    match = _TRASH_START.match(value)
    if match is None:
        return None
    lowered = " ".join(value.casefold().split())
    if re.search(r"\b(?:permanently\s+delete|delete\s+permanently|remove\s+permanently)\b", lowered):
        return None
    remainder = value[match.end():].strip()
    remainder = re.sub(r"^(?:file\s+)?(?:at\s+)?(?:path\s+)?", "", remainder, flags=re.I)
    return _write_path_argument(remainder)


def _conversation_turn_groups(history: list[dict]) -> list[list[dict]]:
    """Keep each user turn and its tool trace atomic during context trimming."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for message in history:
        if message.get("role") == "user" and current:
            groups.append(current)
            current = []
        current.append(message)
    if current:
        groups.append(current)
    return groups


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(right)
    )


def _mentions_filename(lowered_text: str, filename: str) -> bool:
    return re.search(
        rf"(?<![\w.-]){re.escape(filename.casefold())}(?![\w.-])",
        lowered_text,
    ) is not None


def _render_metadata_results(
    required_calls: tuple[ModelCapabilityCall, ...],
    observed_results: list[tuple],
) -> str:
    by_path = {
        os.path.normcase(os.path.normpath(str(call.arguments.get("path", "")))): result
        for call, result in observed_results
        if call.capability == "filesystem.stat"
    }
    lines = ["Here is the metadata for the requested files:"]
    for required in required_calls:
        requested_path = str(required.arguments["path"])
        name = _safe_filename(Path(requested_path).name)
        result = by_path.get(os.path.normcase(os.path.normpath(requested_path)))
        lines.extend(("", f"- {name}"))
        if result is None:
            lines.append("  - Metadata was not returned.")
            continue
        if not result.success:
            message = (
                result.error.message
                if result.error is not None
                else "The metadata request failed."
            )
            lines.append(f"  - {_safe_text(message)}")
            continue
        output = result.output or {}
        lines.append(f"  - Type: {_safe_text(str(output.get('type', 'unknown')))}")
        size = output.get("size_bytes")
        if isinstance(size, int) and not isinstance(size, bool):
            lines.append(f"  - Size: {size:,} bytes")
        created = output.get("created_at")
        if isinstance(created, str):
            lines.append(f"  - Created: {_safe_text(created)}")
        modified = output.get("modified_at")
        if isinstance(modified, str):
            lines.append(f"  - Modified: {_safe_text(modified)}")
    return "\n".join(lines)


def _render_listing_results(
    _required_calls: tuple[ModelCapabilityCall, ...],
    observed_results: list[tuple],
) -> str:
    result = next(
        (
            observed
            for call, observed in observed_results
            if call.capability == "filesystem.list"
        ),
        None,
    )
    if result is None:
        return "The directory listing was not returned."
    if not result.success:
        message = (
            result.error.message
            if result.error is not None
            else "The directory listing failed."
        )
        return _safe_text(message)
    output = result.output or {}
    entries = output.get("entries")
    if not isinstance(entries, list) or not entries:
        return "The directory is empty."
    lines = ["Here are the entries in the requested directory:"]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        entry_type = _safe_text(str(entry.get("type", "unknown")))
        lines.append(f"- {_safe_filename(entry['name'])} ({entry_type})")
    if output.get("has_more") is True:
        lines.extend(("", "More entries are available on the next page."))
    return "\n".join(lines)


def _render_find_result(
    _required_calls: tuple[ModelCapabilityCall, ...],
    observed_results: list[tuple],
) -> str:
    result = next(
        (
            observed
            for call, observed in observed_results
            if call.capability == "filesystem.find"
        ),
        None,
    )
    if result is None:
        return "The file or folder lookup was not returned."
    if not result.success:
        message = (
            result.error.message
            if result.error is not None
            else "The file or folder lookup failed."
        )
        return _safe_text(message)
    output = result.output or {}
    name = _safe_filename(str(output.get("name", "entry")))
    kind = str(output.get("kind", "any"))
    path = _safe_text(str(output.get("path", "the requested folder")))
    matches = output.get("matches")
    if not isinstance(matches, list) or not matches:
        label = "entry" if kind == "any" else kind
        return f"No {label} named {name} was found in {path}."
    lines = [f"Found {len(matches)} matching entr{'y' if len(matches) == 1 else 'ies'}:"]
    for match in matches:
        if not isinstance(match, dict):
            continue
        entry_type = _safe_text(str(match.get("type", "unknown")))
        entry_path = _safe_text(str(match.get("path", "")))
        lines.append(f"- {entry_type}: {entry_path}")
    return "\n".join(lines)


def _render_text_result(
    _required_calls: tuple[ModelCapabilityCall, ...],
    observed_results: list[tuple],
) -> str:
    call_and_result = next(
        (
            (call, observed)
            for call, observed in observed_results
            if call.capability == "filesystem.read_text"
        ),
        None,
    )
    if call_and_result is None:
        return "The text-file content was not returned."
    call, result = call_and_result
    if not result.success:
        message = (
            result.error.message
            if result.error is not None
            else "The text-file read failed."
        )
        return _safe_text(message)
    output = result.output or {}
    text = output.get("text")
    if not isinstance(text, str):
        return "The text-file read returned an invalid result."
    name = _safe_filename(Path(str(call.arguments.get("path", "file"))).name)
    if not text:
        answer = f"{name} is empty."
    else:
        fence = _markdown_code_fence(text)
        closing_prefix = "" if text.endswith(("\n", "\r")) else "\n"
        answer = f"Here is the content of {name}:\n\n{fence}text\n{text}{closing_prefix}{fence}"
    if output.get("truncated_by_bytes") is True or output.get("truncated_by_lines") is True:
        answer += "\n\nThe displayed content was truncated by the configured read limit."
    return answer


def _render_search_result(
    _required_calls: tuple[ModelCapabilityCall, ...],
    observed_results: list[tuple],
) -> str:
    result = next(
        (
            observed
            for call, observed in observed_results
            if call.capability == "filesystem.search"
        ),
        None,
    )
    if result is None:
        return "The search results were not returned."
    if not result.success:
        message = (
            result.error.message
            if result.error is not None
            else "The filesystem search failed."
        )
        return _safe_text(message)
    output = result.output or {}
    query = _safe_text(str(output.get("query", "")))
    matches = output.get("matches")
    if not isinstance(matches, list) or not matches:
        return f"No matches were found for {_safe_text(query)!r}."
    lines = [f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} for {_safe_text(query)!r}:"]
    for match in matches:
        if not isinstance(match, dict):
            continue
        relative_path = _safe_filename(str(match.get("relative_path", "file")))
        line_number = match.get("line_number")
        line_label = line_number if isinstance(line_number, int) and not isinstance(line_number, bool) else "?"
        snippet = _safe_text(str(match.get("snippet", "")))
        lines.append(f"- {relative_path}:{line_label}: {snippet}")
    notices: list[str] = []
    if output.get("truncated_by_matches") is True:
        notices.append("More matches exist beyond the configured match limit.")
    if isinstance(output.get("truncated_files"), int) and output["truncated_files"]:
        notices.append("Some files were searched only up to the configured byte limit.")
    if isinstance(output.get("skipped_files"), int) and output["skipped_files"]:
        notices.append("Some files were skipped because they were inaccessible or not UTF text.")
    if notices:
        lines.extend(("", *notices))
    return "\n".join(lines)


def _markdown_code_fence(text: str) -> str:
    longest_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", text)),
        default=0,
    )
    return "`" * max(3, longest_run + 1)


def _safe_filename(value: str) -> str:
    return _safe_text(value).replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*")


def _safe_text(value: str) -> str:
    return "".join(character if character >= " " else "�" for character in str(value))


def _explicit_windows_path(text: str) -> str | None:
    value = str(text)
    quoted = re.search(r"[\"']([A-Za-z]:[\\/][^\"']+)[\"']", value)
    if quoted is not None:
        return quoted.group(1).strip()
    unquoted = re.search(r"(?i)([a-z]:[\\/].+)$", value)
    if unquoted is None:
        return None
    candidate = re.split(
        r"(?i)\s+(?:and\s+(?:report|show|tell|list|give)|then|please)\b",
        unquoted.group(1),
        maxsplit=1,
    )[0].strip().rstrip("?!.,;:\"'")
    return candidate or None


def _is_listing_request(lowered: str) -> bool:
    return bool(
        re.search(r"\bfilesystem[.]list\b", lowered)
        or re.search(
            r"\b(?:list|show|display)\b.{0,80}\b"
            r"(?:files?|folders?|director(?:y|ies)|entries|contents|items)\b",
            lowered,
        )
        or re.search(r"\b(?:what|which)\s+(?:files?|folders?|directories|entries|items)\b", lowered)
        or re.search(
            r"\b(?:files?|folders?|directories|entries|items)\s+"
            r"(?:do\s+i\s+have|are\s+(?:in|inside|under|there))\b",
            lowered,
        )
        or re.search(r"\b(?:contents|entries)\s+(?:of|in|inside)\b", lowered)
        or re.search(r"\b(?:show\s+me\s+)?what\s+is\s+in\b", lowered)
    )


def _is_text_read_request(lowered: str) -> bool:
    return bool(
        re.search(r"\bfilesystem[.]read_text\b", lowered)
        or re.search(r"\b(?:read|open|summarize)\s+", lowered)
        or re.search(
            r"\b(?:show|display)\b.{0,40}\b(?:contents?|text)\b",
            lowered,
        )
        or re.search(
            r"\b(?:what(?:'s|\s+is)|tell\s+me\s+what(?:'s|\s+is))\b"
            r".{0,40}\b(?:in|inside)\b",
            lowered,
        )
    )


def _is_search_request(lowered: str) -> bool:
    return bool(
        re.search(r"\bfilesystem[.]search\b", lowered)
        or re.search(r"\b(?:search|find|look\s+for)\b", lowered)
        or re.search(r"\b(?:files?|documents?)\b.{0,60}\b(?:containing|matching)\b", lowered)
    )


def _find_target(
    text: str,
    host_access_policy: HostAccessPolicy | None,
) -> tuple[str, str, str] | None:
    value = str(text).strip()
    lowered = " ".join(value.casefold().split())
    if not _is_find_name_request(lowered):
        return None
    name = _find_requested_name(value)
    if not name:
        return None
    path = _find_base_path(value, host_access_policy)
    if path is None:
        return None
    kind = _find_requested_kind(lowered)
    return str(path), name, kind


def _is_find_name_request(lowered: str) -> bool:
    if re.search(r"\bfilesystem[.]find\b", lowered):
        return True
    if re.search(r"\b(?:called|named)\b", lowered) and re.search(
        r"\b(?:find|locate|where|folder|directory|file|document)\b",
        lowered,
    ):
        return True
    if re.search(r"\b(?:find|locate)\b.{0,60}\b(?:folder|directory|file|document)\b", lowered):
        return True
    return False


def _find_requested_kind(lowered: str) -> str:
    if re.search(r"\b(?:folders?|directories|directory)\b", lowered):
        return "directory"
    if re.search(r"\b(?:files?|documents?)\b", lowered):
        return "file"
    return "any"


def _find_requested_name(value: str) -> str | None:
    patterns = (
        r"(?is)\b(?:called|named)\s+[\"']([^\"'\\/\r\n]+)[\"']",
        r"(?is)\b(?:called|named)\s+([^,;?!\\/\r\n]+)",
        r"(?is)\b(?:folder|directory|file|document)\s+[\"']([^\"'\\/\r\n]+)[\"']",
        r"(?is)\b(?:find|locate)\s+(?:the\s+)?(?:folder|directory|file|document)\s+([^,;?!\\/\r\n]+?)\s+\b(?:on|in|inside|under)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match is None:
            continue
        name = _clean_find_name(match.group(1))
        if name:
            return name
    return None


def _clean_find_name(value: str) -> str:
    name = str(value).strip().strip("\"'").strip()
    name = re.sub(r"(?is)\s+\b(?:find|locate)\s+it\b.*$", "", name).strip()
    name = re.sub(
        r"(?is)\s+\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?"
        r"(?:desktop|downloads|documents|home)(?:\s+(?:folder|directory))?\b.*$",
        "",
        name,
    ).strip()
    name = re.sub(r"(?is)^(?:a|an|the)\s+", "", name).strip()
    name = name.rstrip(".").strip()
    if (
        not name
        or len(name) > 255
        or "\x00" in name
        or any(separator in name for separator in ("/", "\\"))
        or name in {".", ".."}
    ):
        return ""
    return name


def _find_base_path(
    value: str,
    host_access_policy: HostAccessPolicy | None,
) -> Path | None:
    explicit_path = _explicit_windows_path(value)
    if explicit_path is not None:
        return Path(explicit_path)
    alias = _known_folder_alias(value)
    if alias is None or host_access_policy is None:
        return None
    user_home = getattr(host_access_policy, "user_home", None)
    if not isinstance(user_home, Path):
        return None
    if alias == "home":
        return user_home
    return user_home / alias


def _known_folder_alias(value: str) -> str | None:
    lowered = " ".join(str(value).casefold().split())
    if re.search(r"\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?desktop(?:\s+folder)?\b", lowered):
        return "Desktop"
    if re.search(r"\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?downloads(?:\s+folder)?\b", lowered):
        return "Downloads"
    if re.search(r"\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?documents(?:\s+folder)?\b", lowered):
        return "Documents"
    if re.search(r"\b(?:in|inside|under)\s+(?:my\s+)?home(?:\s+folder|\s+directory)?\b", lowered):
        return "home"
    return None


def _search_target_and_query(text: str) -> tuple[str, str] | None:
    value = str(text).strip()
    lowered = " ".join(value.casefold().split())
    if not _is_search_request(lowered):
        return None

    quoted_path = re.search(r"[\"']([A-Za-z]:[\\/][^\"']+)[\"']", value)
    if quoted_path is not None:
        path = quoted_path.group(1).strip()
        query = _first_quoted_search_query(value, path)
        if query is None:
            query = _query_around_path(value, path)
        return (path, query) if query else None

    path_then_query = re.search(
        r"(?is)\b(?:search|find)\b\s+([a-z]:[\\/].+?)\s+\b(?:for|containing|matching)\s+(.+)$",
        value,
    )
    if path_then_query is not None:
        path = path_then_query.group(1).strip().rstrip("?!.,;:\"'")
        query = _clean_search_query(path_then_query.group(2))
        return (path, query) if path and query else None

    query_then_path = re.search(
        r"(?is)\b(?:search|find|look\s+for)\b(?:\s+for)?\s+(.+?)\s+\b(?:in|inside|under|within)\s+([a-z]:[\\/].+)$",
        value,
    )
    if query_then_path is not None:
        query = _clean_search_query(query_then_path.group(1))
        path = query_then_path.group(2).strip().rstrip("?!.,;:\"'")
        return (path, query) if path and query else None

    return None


def _first_quoted_search_query(value: str, path: str) -> str | None:
    for match in re.finditer(r"[\"']([^\"']+)[\"']", value):
        candidate = match.group(1).strip()
        if candidate.casefold() == path.casefold():
            continue
        if re.search(r"(?i)^[a-z]:[\\/]", candidate):
            continue
        query = _clean_search_query(candidate)
        if query:
            return query
    return None


def _query_around_path(value: str, path: str) -> str | None:
    escaped_path = re.escape(path)
    after = re.search(rf"(?is){escaped_path}[\"']?\s+\b(?:for|containing|matching)\s+(.+)$", value)
    if after is not None:
        return _clean_search_query(after.group(1))
    before = re.search(
        rf"(?is)\b(?:search|find|look\s+for)\b(?:\s+for)?\s+(.+?)\s+\b(?:in|inside|under|within)\s+[\"']?{escaped_path}",
        value,
    )
    if before is not None:
        return _clean_search_query(before.group(1))
    return None


def _clean_search_query(value: str) -> str:
    query = str(value).strip().strip("\"'").strip().rstrip("?!.,;")
    query = re.sub(r"(?i)^(?:literal\s+)?(?:text|phrase|string)\s+", "", query).strip()
    if "\x00" in query or len(query) > 512:
        return ""
    return query
