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


@dataclass(slots=True)
class _ActiveFoundDirectory:
    path: str
    name: str


@dataclass(slots=True)
class _PendingTextRead:
    path: str
    name: str


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
        self._active_found_directory: _ActiveFoundDirectory | None = None
        self._last_filesystem_operation: str | None = None
        self._pending_text_read: _PendingTextRead | None = None
        self._awaiting_folder_path = False
        # Capability calls/results stay only in memory for coherent follow-ups.
        # ConversationStore intentionally persists user and final assistant text only.
        self._agent_history = self.store.messages()
        self._restored_filesystem_context = False
        if self.agent_enabled:
            self._restore_filesystem_context_from_history()

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
            self._awaiting_folder_path = False
            capability_turn = self.agent_enabled
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

                    turn_capabilities = self._planner_capabilities()
                    forced_answer = self._run_desktop_child_folder_creation(
                        text,
                        source,
                        activity,
                        turn_id,
                        turn_capabilities,
                        retain_results,
                        turn_results,
                    )
                    if forced_answer is not None:
                        answer = forced_answer
                        result = None
                    else:
                        required_calls = self._continuation_required_calls(text)
                        if required_calls:
                            self._restored_filesystem_context = False
                        result = self.agent_runtime.run(
                            self._model_messages(
                                capability_turn=True,
                                capability_names=turn_capabilities,
                            ),
                            session_id=self._session_id,
                            turn_id=turn_id,
                            portable_root=self.portable_root,
                            allowed_read_roots=self.allowed_read_roots,
                            host_access_policy=self.host_access_policy,
                            cancellation=source.token,
                            result_observer=retain_results,
                            capability_names=turn_capabilities,
                            required_calls=required_calls,
                            continue_after_required_calls=False,
                        )
                else:
                    result = self.agent_runtime.run_conversation(
                        self._model_messages(capability_turn=False),
                        cancellation=source.token,
                    )
                    forced_answer = None
                if result is None:
                    answer = forced_answer or ""
                elif result.status == AgentRunStatus.CANCELLED:
                    return "The response was stopped."
                elif result.status != AgentRunStatus.COMPLETED:
                    raise RuntimeError(
                        result.message or "The bounded agent run did not complete."
                    )
                else:
                    answer = result.assistant_text.strip()
                    recovered_read_answer = self._run_named_file_read_recovery(
                        text,
                        answer,
                        source,
                        activity,
                        turn_id,
                        turn_capabilities,
                        retain_results,
                        turn_results,
                    )
                    if recovered_read_answer is not None:
                        answer = recovered_read_answer
                    self._retain_pending_text_read_context(text, answer, turn_results)
                    fallback_answer = self._fallback_required_answer(required_calls, turn_results)
                    if forced_answer is not None:
                        answer = forced_answer
                    elif fallback_answer is not None:
                        answer = fallback_answer
                    else:
                        grounded_answer = _grounded_text_read_answer(text, answer, turn_results)
                        if grounded_answer is not None:
                            answer = grounded_answer
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

    def _planner_capabilities(self) -> tuple[str, ...]:
        return self.agent_capabilities

    def _fallback_required_answer(
        self,
        required_calls: tuple[ModelCapabilityCall, ...],
        turn_results: list[tuple],
    ) -> str | None:
        if not required_calls or not _observed_required_calls_complete(
            required_calls,
            turn_results,
        ):
            return None
        if all(call.capability == "filesystem.stat" for call in required_calls):
            return _render_metadata_results(required_calls, turn_results)
        if all(call.capability == "filesystem.find" for call in required_calls):
            return _render_find_result(required_calls, turn_results)
        if all(call.capability == "filesystem.list" for call in required_calls):
            return _render_listing_results(required_calls, turn_results)
        if all(call.capability == "filesystem.read_text" for call in required_calls):
            return _render_text_result(required_calls, turn_results)
        if all(call.capability == "filesystem.search" for call in required_calls):
            return _render_search_result(required_calls, turn_results)
        return None

    def _run_desktop_child_folder_creation(
        self,
        text: str,
        source: CancellationSource,
        activity,
        turn_id: str,
        turn_capabilities: tuple[str, ...],
        retain_results,
        turn_results: list[tuple],
    ) -> str | None:
        request = _desktop_child_folder_creation_request(text)
        if request is None:
            return None
        if not {"filesystem.find", "filesystem.mkdir"}.issubset(self.agent_capabilities):
            return None
        parent_name, child_name = request
        find_call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-mkdir-parent",
            capability="filesystem.find",
            arguments={"path": "Desktop", "name": parent_name, "kind": "directory"},
        )
        if activity:
            activity("Finding parent folder...")
        find_start = len(turn_results)
        result = self.agent_runtime.run(
            self._model_messages(
                capability_turn=True,
                capability_names=turn_capabilities,
            ),
            session_id=self._session_id,
            turn_id=turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            result_observer=retain_results,
            capability_names=turn_capabilities,
            required_calls=(find_call,),
            continue_after_required_calls=False,
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "The response was stopped."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "The parent folder lookup did not complete.")
        find_results = turn_results[find_start:]
        find_result = next(
            (
                observed
                for call, observed in find_results
                if call.capability == "filesystem.find"
            ),
            None,
        )
        if find_result is None:
            raise RuntimeError("The parent folder lookup result was not returned.")
        if not find_result.success:
            return _render_find_result((find_call,), find_results)
        output = find_result.output or {}
        matches = output.get("matches")
        if not isinstance(matches, list) or len(matches) != 1:
            return _render_find_result((find_call,), find_results)
        parent_path = matches[0].get("path") if isinstance(matches[0], dict) else None
        if not isinstance(parent_path, str) or not parent_path:
            return "The parent folder lookup did not return an exact folder path."
        mkdir_call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-mkdir-child",
            capability="filesystem.mkdir",
            arguments={"path": str(Path(parent_path) / child_name)},
        )
        if activity:
            activity("Preparing folder approval...")
        mkdir_start = len(turn_results)
        result = self.agent_runtime.run(
            self._model_messages(
                capability_turn=True,
                capability_names=turn_capabilities,
            ),
            session_id=self._session_id,
            turn_id=turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            result_observer=retain_results,
            capability_names=turn_capabilities,
            required_calls=(mkdir_call,),
            continue_after_required_calls=False,
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "The response was stopped."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "Folder creation did not complete.")
        mkdir_result = next(
            (
                observed
                for call, observed in turn_results[mkdir_start:]
                if call.capability == "filesystem.mkdir"
            ),
            None,
        )
        if mkdir_result is None:
            raise RuntimeError("The folder creation result was not returned.")
        if not mkdir_result.success:
            return (
                mkdir_result.error.message
                if mkdir_result.error is not None
                else "The folder could not be created."
            )
        output = mkdir_result.output or {}
        return f"Created empty folder: {output['path']}"

    def _run_named_file_read_recovery(
        self,
        text: str,
        assistant_text: str,
        source: CancellationSource,
        activity,
        turn_id: str,
        turn_capabilities: tuple[str, ...],
        retain_results,
        turn_results: list[tuple],
    ) -> str | None:
        if not _assistant_requests_file_path_for_text_read(assistant_text):
            return None
        target = _find_target(text, self.host_access_policy)
        if target is None or target[2] != "file":
            return None
        if not {"filesystem.find", "filesystem.read_text"}.issubset(self.agent_capabilities):
            return None
        directory, requested_name, _kind = target
        find_call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-read-find",
            capability="filesystem.find",
            arguments={"path": directory, "name": requested_name, "kind": "file"},
        )
        if activity:
            activity("Finding file...")
        find_start = len(turn_results)
        result = self.agent_runtime.run(
            self._model_messages(
                capability_turn=True,
                capability_names=turn_capabilities,
            ),
            session_id=self._session_id,
            turn_id=turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            result_observer=retain_results,
            capability_names=turn_capabilities,
            required_calls=(find_call,),
            continue_after_required_calls=False,
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "The response was stopped."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "The file lookup did not complete.")
        find_results = turn_results[find_start:]
        find_result = next(
            (
                observed
                for call, observed in find_results
                if call.capability == "filesystem.find"
            ),
            None,
        )
        if find_result is None:
            raise RuntimeError("The file lookup result was not returned.")
        if not find_result.success:
            return _render_find_result((find_call,), find_results)
        output = find_result.output or {}
        matches = output.get("matches")
        if isinstance(matches, list):
            file_matches = [
                match
                for match in matches
                if isinstance(match, dict)
                and match.get("type") == "file"
                and isinstance(match.get("path"), str)
            ]
            if len(file_matches) == 1:
                return self._run_required_text_read(
                    file_matches[0]["path"],
                    source,
                    activity,
                    turn_id,
                    turn_capabilities,
                    retain_results,
                    turn_results,
                )
            if len(file_matches) > 1:
                return _multiple_file_candidates_answer(
                    requested_name,
                    directory,
                    tuple(match["path"] for match in file_matches),
                )
        if "filesystem.list" not in self.agent_capabilities:
            return _render_find_result((find_call,), find_results)
        list_call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-read-list",
            capability="filesystem.list",
            arguments={"path": directory},
        )
        if activity:
            activity("Checking folder...")
        list_start = len(turn_results)
        result = self.agent_runtime.run(
            self._model_messages(
                capability_turn=True,
                capability_names=turn_capabilities,
            ),
            session_id=self._session_id,
            turn_id=turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            result_observer=retain_results,
            capability_names=turn_capabilities,
            required_calls=(list_call,),
            continue_after_required_calls=False,
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "The response was stopped."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "The folder listing did not complete.")
        list_results = turn_results[list_start:]
        list_result = next(
            (
                observed
                for call, observed in list_results
                if call.capability == "filesystem.list"
            ),
            None,
        )
        if list_result is None:
            raise RuntimeError("The folder listing result was not returned.")
        if not list_result.success:
            return _render_listing_results((list_call,), list_results)
        output = list_result.output or {}
        entries = output.get("entries")
        candidates = (
            _disambiguated_file_candidates(requested_name, entries)
            if isinstance(entries, list)
            else []
        )
        read_directory = output.get("path") if isinstance(output.get("path"), str) else directory
        if len(candidates) == 1:
            return self._run_required_text_read(
                str(Path(read_directory) / candidates[0]),
                source,
                activity,
                turn_id,
                turn_capabilities,
                retain_results,
                turn_results,
            )
        if len(candidates) > 1:
            return _multiple_file_candidates_answer(
                requested_name,
                read_directory,
                tuple(str(Path(read_directory) / name) for name in candidates),
            )
        return _render_find_result((find_call,), find_results)

    def _run_required_text_read(
        self,
        path: str,
        source: CancellationSource,
        activity,
        turn_id: str,
        turn_capabilities: tuple[str, ...],
        retain_results,
        turn_results: list[tuple],
    ) -> str:
        read_call = ModelCapabilityCall(
            provider_call_id=f"required-{self._turn_number}-read-text",
            capability="filesystem.read_text",
            arguments={"path": path},
        )
        if activity:
            activity("Reading file...")
        read_start = len(turn_results)
        result = self.agent_runtime.run(
            self._model_messages(
                capability_turn=True,
                capability_names=turn_capabilities,
            ),
            session_id=self._session_id,
            turn_id=turn_id,
            portable_root=self.portable_root,
            allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy,
            cancellation=source.token,
            result_observer=retain_results,
            capability_names=turn_capabilities,
            required_calls=(read_call,),
            continue_after_required_calls=False,
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "The response was stopped."
        if result.status != AgentRunStatus.COMPLETED:
            raise RuntimeError(result.message or "The text read did not complete.")
        return _render_text_result((read_call,), turn_results[read_start:])

    def _continuation_required_calls(
        self,
        text: str,
    ) -> tuple[ModelCapabilityCall, ...]:
        pending_text_read = self._pending_text_read_target(text)
        if (
            pending_text_read is not None
            and "filesystem.read_text" in self.agent_capabilities
        ):
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.read_text",
                    arguments={"path": pending_text_read},
                ),
            )
        if "filesystem.list" not in self.agent_capabilities:
            return ()
        active_directory = None
        active_directory = self._active_directory_listing_target(
            " ".join(str(text).casefold().split())
        )
        if active_directory is None:
            return ()
        return (
            ModelCapabilityCall(
                provider_call_id=f"required-{self._turn_number}-1",
                capability="filesystem.list",
                arguments={"path": active_directory},
            ),
        )

    def _restore_filesystem_context_from_history(self) -> None:
        if (
            self.host_access_policy is None
            or not self._agent_history
            or not {"filesystem.list", "filesystem.read_text"} & set(self.agent_capabilities)
        ):
            return
        restored_history: list[dict] = []
        restored_any = False
        trace_index = 0
        for group in _conversation_turn_groups(self._agent_history):
            if not group:
                continue
            first = group[0]
            if first.get("role") != "user":
                restored_history.extend(group)
                continue
            assistant = next(
                (message for message in group[1:] if message.get("role") == "assistant"),
                None,
            )
            context = None
            if assistant is not None and "filesystem.list" in self.agent_capabilities:
                context = _restored_listing_context(
                    str(first.get("content", "")),
                    str(assistant.get("content", "")),
                    self.host_access_policy,
                )
            restored_history.append(first)
            pending_text_read = None
            if assistant is not None and "filesystem.read_text" in self.agent_capabilities:
                pending_text_read = _restored_pending_text_read(
                    str(first.get("content", "")),
                    str(assistant.get("content", "")),
                    self.host_access_policy,
                )
            if context is not None:
                trace_index += 1
                path, entries = context
                call = ModelCapabilityCall(
                    provider_call_id=f"restored-list-{trace_index}",
                    capability="filesystem.list",
                    arguments={"path": path},
                )
                result = _restored_listing_result(call.provider_call_id, path, entries)
                restored_history.append(model_capability_calls_message((call,)))
                restored_history.append(model_capability_result_message(call, result))
                files = tuple(
                    entry["name"]
                    for entry in entries
                    if entry.get("type") == "file" and isinstance(entry.get("name"), str)
                )
                self._active_found_directory = _ActiveFoundDirectory(path=path, name=Path(path).name)
                self._active_listing = _ActiveDirectoryListing(path=path, files=files)
                self._last_filesystem_operation = "listing"
                restored_any = True
            if pending_text_read is not None:
                path, name = pending_text_read
                self._pending_text_read = _PendingTextRead(path=path, name=name)
                restored_any = True
            restored_history.extend(group[1:])
        if restored_any:
            self._agent_history = restored_history
            self._restored_filesystem_context = True

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
            self._model_messages(
                capability_turn=True,
                capability_names=self._planner_capabilities(),
            ),
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=self._planner_capabilities(),
            continue_after_required_calls=True,
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "Folder creation was cancelled before execution."
        if not observed:
            if result.status != AgentRunStatus.COMPLETED:
                raise RuntimeError(result.message or "Folder creation did not complete.")
            raise RuntimeError("The folder creation result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            fallback = outcome.error.message if outcome.error else "The folder could not be created."
            return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback
        self._active_listing = None
        fallback = f"Created empty folder: {outcome.output['path']}"
        return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback

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
            self._model_messages(
                capability_turn=True,
                capability_names=self._planner_capabilities(),
            ),
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=self._planner_capabilities(),
            continue_after_required_calls=True,
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "Text-file writing was cancelled before execution."
        if not observed:
            if result.status != AgentRunStatus.COMPLETED:
                raise RuntimeError(result.message or "Text-file writing did not complete.")
            raise RuntimeError("The text-file write result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            fallback = outcome.error.message if outcome.error else "The text file could not be written."
            return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback
        self._active_listing = None
        output = outcome.output or {}
        fallback = f"Wrote text file: {output['path']} ({output['bytes_written']:,} bytes, {output['operation']})."
        return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback

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
            self._model_messages(
                capability_turn=True,
                capability_names=self._planner_capabilities(),
            ),
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=self._planner_capabilities(),
            continue_after_required_calls=True,
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "File copying was cancelled before execution."
        if not observed:
            if result.status != AgentRunStatus.COMPLETED:
                raise RuntimeError(result.message or "File copying did not complete.")
            raise RuntimeError("The file-copy result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            fallback = outcome.error.message if outcome.error else "The file could not be copied."
            return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback
        self._active_listing = None
        output = outcome.output or {}
        fallback = (f"Copied file: {output['destination_path']} "
                    f"({output['bytes_copied']:,} bytes, {output['operation']}).")
        return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback

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
            self._model_messages(
                capability_turn=True,
                capability_names=self._planner_capabilities(),
            ),
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=self._planner_capabilities(),
            continue_after_required_calls=True,
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "File moving was cancelled before execution."
        if not observed:
            if result.status != AgentRunStatus.COMPLETED:
                raise RuntimeError(result.message or "File moving did not complete.")
            raise RuntimeError("The file-move result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            fallback = outcome.error.message if outcome.error else "The file could not be moved."
            return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback
        self._active_listing = None
        output = outcome.output or {}
        fallback = (f"Moved file: {output['destination_path']} "
                    f"({output['bytes_moved']:,} bytes, {output['operation']}).")
        return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback

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
            self._model_messages(
                capability_turn=True,
                capability_names=self._planner_capabilities(),
            ),
            session_id=self._session_id, turn_id=f"turn-{self._turn_number}",
            portable_root=self.portable_root, allowed_read_roots=self.allowed_read_roots,
            host_access_policy=self.host_access_policy, cancellation=source.token,
            required_calls=(call,), capability_names=self._planner_capabilities(),
            continue_after_required_calls=True,
            result_observer=lambda calls, results: observed.extend(results),
        )
        if result.status == AgentRunStatus.CANCELLED:
            return "File trashing was cancelled before execution."
        if not observed:
            if result.status != AgentRunStatus.COMPLETED:
                raise RuntimeError(result.message or "File trashing did not complete.")
            raise RuntimeError("The file-trash result was not returned.")
        outcome = observed[0]
        if not outcome.success:
            fallback = outcome.error.message if outcome.error else "The file could not be sent to the Recycle Bin."
            return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback
        self._active_listing = None
        output = outcome.output or {}
        fallback = f"Sent file to Recycle Bin: {output['path']} ({output['bytes_trashed']:,} bytes)."
        return result.assistant_text.strip() if result.status == AgentRunStatus.COMPLETED else fallback

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
            self._active_found_directory = None
            self._last_filesystem_operation = None
            self._pending_text_read = None
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
        capability_names: tuple[str, ...] | None = None,
    ) -> list[dict]:
        planner_capabilities = (
            capability_names if capability_names is not None else self._read_capabilities()
        )
        prompt = (
            (
                agent_system_prompt(
                    self.host_read_scope or HostReadScope.PORTABLE_ROOT,
                    planner_capabilities,
                    user_home=(
                        str(self.host_access_policy.user_home)
                        if self.host_access_policy is not None
                        else None
                    ),
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
            if self._active_directory_listing_target(lowered) is not None:
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
        active_directory = self._active_directory_listing_target(lowered)
        if (
            active_directory is not None
            and "filesystem.list" in self.agent_capabilities
        ):
            return (
                ModelCapabilityCall(
                    provider_call_id=f"required-{self._turn_number}-1",
                    capability="filesystem.list",
                    arguments={"path": active_directory},
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

    def _pending_text_read_target(self, text: str) -> str | None:
        pending = self._pending_text_read
        if pending is None:
            return None
        lowered = " ".join(str(text).casefold().split())
        if _is_affirmative(lowered):
            return pending.path
        if not _is_text_read_request(lowered):
            return None
        if re.search(r"\b(?:it|this|that|the\s+file|contents?)\b", lowered):
            return pending.path
        if _mentions_filename(lowered, pending.name) or _mentions_filename(lowered, Path(pending.name).stem):
            return pending.path
        return None

    def _active_directory_listing_target(self, lowered: str) -> str | None:
        if self._active_found_directory is None and self._active_listing is None:
            return None
        affirmative = _is_affirmative(lowered)
        if affirmative is None and not (
            _is_listing_request(lowered)
            and re.search(r"\b(?:it|there|that|this|inside|in\s+it|what(?:'s|\s+is)\s+in)\b", lowered)
        ):
            return None
        if affirmative is not None and self._last_filesystem_operation != "find":
            return None
        if self._active_found_directory is not None:
            return self._active_found_directory.path
        if self._active_listing is not None:
            return self._active_listing.path
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
            if call.capability == "filesystem.read_text" and result.success:
                self._pending_text_read = None
            if not result.success or not isinstance(result.output, dict):
                continue
            output = result.output
            if call.capability == "filesystem.list":
                path = output.get("path")
                entries = output.get("entries")
                if not isinstance(path, str) or not isinstance(entries, list):
                    continue
                self._active_found_directory = _ActiveFoundDirectory(
                    path=path,
                    name=Path(path).name,
                )
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
            if call.capability == "filesystem.find":
                matches = output.get("matches")
                if not isinstance(matches, list):
                    continue
                directories = [
                    match
                    for match in matches
                    if isinstance(match, dict)
                    and match.get("type") == "directory"
                    and isinstance(match.get("path"), str)
                    and isinstance(match.get("name"), str)
                ]
                if len(directories) == 1:
                    self._active_found_directory = _ActiveFoundDirectory(
                        path=directories[0]["path"],
                        name=directories[0]["name"],
                    )
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

    def _retain_pending_text_read_context(
        self,
        user_text: str,
        assistant_text: str,
        turn_results: list[tuple],
    ) -> None:
        if _latest_successful_text_read(turn_results) is not None:
            self._pending_text_read = None
            return
        lowered = " ".join(str(user_text).casefold().split())
        if not (
            _is_text_read_request(lowered)
            or _assistant_requests_text_read_confirmation(assistant_text)
        ):
            return
        path = _pending_text_read_path_from_results(turn_results)
        if path is not None:
            self._pending_text_read = _PendingTextRead(path=path, name=Path(path).name)

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


def _desktop_child_folder_creation_request(text: str) -> tuple[str, str] | None:
    value = str(text).strip()
    lowered = " ".join(value.casefold().split())
    if not re.search(r"\b(?:create|make)\b", lowered):
        return None
    if not re.search(r"\b(?:folder|directory)\b", lowered):
        return None
    if not re.search(r"\b(?:in|inside|under)\s+(?:it|that|this|the\s+(?:folder|directory))\b", lowered):
        return None
    parent_name = None
    parent_patterns = (
        r"(?is)\b(?:folder|directory)\s+(?:on|in|inside|under)\s+(?:my\s+|the\s+)?"
        r"desktop(?:\s+(?:folder|directory))?\s+(?:called|named)\s+"
        r"(?P<name>.+?)(?=(?:[.?!,;]\s*)?\b(?:create|make)\b|[.?!,;]|$)",
        r"(?is)\b(?:folder|directory)\s+(?:called|named)\s+"
        r"(?P<name>.+?)\s+\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?"
        r"desktop(?:\s+(?:folder|directory))?\b",
    )
    for pattern in parent_patterns:
        match = re.search(pattern, value)
        if match is None:
            continue
        parent_name = _clean_local_entry_name(match.group("name"))
        if parent_name:
            break
    if not parent_name:
        return None
    child_match = re.search(
        r"(?is)\b(?:create|make)\s+(?:(?:a|an|new|empty)\s+)*"
        r"(?:folder|directory)\s+(?:in|inside|under)\s+"
        r"(?:it|that|this|the\s+(?:folder|directory))\s+"
        r"(?:called|named)\s+(?P<name>[^,;?!\\/\r\n]+?)(?=\s*(?:[.?!,;]|$))",
        value,
    )
    if child_match is None:
        return None
    child_name = _clean_local_entry_name(child_match.group("name"))
    if not child_name:
        return None
    return parent_name, child_name


def _clean_local_entry_name(value: str) -> str:
    name = _clean_find_name(value)
    if ":" in name or re.search(r"\b(?:and|then)\b", name, re.I):
        return ""
    return name


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


def _restored_listing_context(
    user_text: str,
    assistant_text: str,
    host_access_policy: HostAccessPolicy,
) -> tuple[str, tuple[dict, ...]] | None:
    lowered_user = " ".join(str(user_text).casefold().split())
    if not _is_listing_request(lowered_user):
        return None
    entries = _visible_listing_entries(assistant_text)
    if entries is None:
        return None
    find_target = _find_target(user_text, host_access_policy)
    if find_target is not None and find_target[2] == "directory":
        containing_path, name, _kind = find_target
        return str(Path(containing_path) / name), entries
    requested_path = _explicit_windows_path(user_text)
    if requested_path is not None:
        return requested_path, entries
    return None


def _restored_pending_text_read(
    user_text: str,
    assistant_text: str,
    host_access_policy: HostAccessPolicy,
) -> tuple[str, str] | None:
    lowered_user = " ".join(str(user_text).casefold().split())
    if not _is_text_read_request(lowered_user):
        return None
    if not _assistant_requests_text_read_confirmation(assistant_text):
        return None
    base_path = _find_base_path(user_text, host_access_policy)
    if base_path is None:
        return None
    name = _visible_file_name(assistant_text)
    if name is None:
        return None
    return str(base_path / name), name


def _visible_file_name(text: str) -> str | None:
    for pattern in (
        r"\bfile\s+name\s+is\s+[\"`'](?P<name>[^\"`'\r\n]{1,255})[\"`']",
        r"\bfile\s+(?:is|named|called)\s+[\"`'](?P<name>[^\"`'\r\n]{1,255})[\"`']",
    ):
        match = re.search(pattern, str(text), re.I)
        if match is not None:
            return _restored_entry_name(match.group("name"))
    return None


def _visible_listing_entries(text: str) -> tuple[dict, ...] | None:
    value = str(text)
    lowered = " ".join(value.casefold().split())
    if re.search(
        r"\b(?:does\s+not\s+exist|could\s+not|couldn't|cannot|can't|permission|denied|specify\s+a\s+directory)\b",
        lowered,
    ):
        return None
    entries = tuple(
        entry
        for entry in (_visible_listing_entry(line) for line in value.splitlines())
        if entry is not None
    )
    if entries:
        return entries
    if re.search(r"\b(?:directory|folder)\s+is\s+empty\b", lowered):
        return ()
    if re.search(r"\bcontains\s+no\s+(?:files?|folders?|directories|items|entries)\b", lowered):
        return ()
    return None


def _visible_listing_entry(line: str) -> dict | None:
    match = re.match(
        r"\s*[-*]\s+`(?P<name>[^`\r\n]{1,255})`(?:\s+\((?P<type>[^()\r\n]+)\))?\s*$",
        str(line),
    )
    if match is None:
        match = re.match(
            r"\s*[-*]\s+(?P<name>[^`()\r\n]{1,255}?)(?:\s+\((?P<type>[^()\r\n]+)\))?\s*$",
            str(line),
        )
    if match is None:
        return None
    name = _restored_entry_name(match.group("name"))
    if name is None:
        return None
    entry_type = _restored_entry_type(name, match.group("type"))
    return {
        "name": name,
        "type": entry_type,
        "is_symlink": entry_type == "symlink",
        "is_reparse_point": False,
    }


def _restored_entry_name(raw_name: str) -> str | None:
    name = str(raw_name).strip()
    if (
        not name
        or name in {".", ".."}
        or "\x00" in name
        or any(separator in name for separator in ("\\", "/", ":"))
    ):
        return None
    return name


def _restored_entry_type(name: str, raw_type: str | None) -> str:
    entry_type = " ".join(str(raw_type or "").casefold().split())
    if entry_type in {"file", "directory", "symlink", "inaccessible", "other"}:
        return entry_type
    return "file" if Path(name).suffix else "directory"


def _restored_listing_result(call_id: str, path: str, entries: tuple[dict, ...]) -> dict:
    return {
        "call_id": call_id,
        "capability": "filesystem.list",
        "success": True,
        "output": {
            "path": path,
            "entries": [dict(entry) for entry in entries],
            "returned_entries": len(entries),
            "total_entries": len(entries),
            "next_cursor": None,
            "has_more": False,
        },
        "error": None,
        "duration_ms": 0,
        "metadata": {"permission": "read", "result_schema_version": 1},
    }


def _pending_text_read_path_from_results(
    observed_results: list[tuple],
) -> str | None:
    found_file = _single_found_file_path(observed_results)
    if found_file is not None:
        return found_file
    return _extensionless_read_candidate_path(observed_results)


def _single_found_file_path(observed_results: list[tuple]) -> str | None:
    for call, result in reversed(observed_results):
        if call.capability != "filesystem.find" or not result.success:
            continue
        output = result.output or {}
        matches = output.get("matches")
        if not isinstance(matches, list):
            continue
        files = [
            match
            for match in matches
            if isinstance(match, dict)
            and match.get("type") == "file"
            and isinstance(match.get("path"), str)
        ]
        if len(files) == 1:
            return files[0]["path"]
    return None


def _extensionless_read_candidate_path(observed_results: list[tuple]) -> str | None:
    for index in range(len(observed_results) - 1, -1, -1):
        call, result = observed_results[index]
        if call.capability != "filesystem.read_text" or result.success:
            continue
        error_code = getattr(result.error, "code", None) if result.error is not None else None
        error_code_value = getattr(error_code, "value", str(error_code))
        if error_code_value != "not_found":
            continue
        raw_path = call.arguments.get("path")
        if not isinstance(raw_path, str):
            continue
        parsed = _extensionless_read_target(raw_path)
        if parsed is None:
            continue
        directory, requested_name = parsed
        for list_call, list_result in observed_results[index + 1:]:
            if list_call.capability != "filesystem.list" or not list_result.success:
                continue
            output = list_result.output or {}
            call_path = list_call.arguments.get("path")
            output_path = output.get("path")
            call_matches = isinstance(call_path, str) and _same_path(call_path, directory)
            output_matches = isinstance(output_path, str) and _same_path(output_path, directory)
            if not (call_matches or output_matches):
                continue
            entries = output.get("entries")
            if not isinstance(entries, list):
                continue
            candidates = _disambiguated_file_candidates(requested_name, entries)
            if len(candidates) != 1:
                continue
            read_directory = output_path if isinstance(output_path, str) else directory
            return str(Path(read_directory) / candidates[0])
    return None


def _extensionless_read_target(path: str) -> tuple[str, str] | None:
    target = Path(path)
    requested_name = target.name
    if (
        not requested_name
        or requested_name in {".", ".."}
        or Path(requested_name).suffix
    ):
        return None
    directory = str(target.parent)
    if not directory or directory == ".":
        return None
    return directory, requested_name


def _disambiguated_file_candidates(requested_name: str, entries: list[dict]) -> list[str]:
    requested_keys = _filename_keys(requested_name)
    candidates: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        if requested_keys & _filename_keys(name):
            candidates.append(name)
    return candidates


def _filename_keys(name: str) -> set[str]:
    value = str(name).strip().casefold()
    stem = Path(value).stem
    return {value, stem, _filename_loose_key(value), _filename_loose_key(stem)} - {""}


def _filename_loose_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _assistant_requests_text_read_confirmation(text: str) -> bool:
    lowered = " ".join(str(text).casefold().split())
    return (
        re.search(r"\bwould\s+you\s+like\b.{0,120}\b(?:see|read|show|display)\b.{0,80}\b(?:contents?|text|file)\b", lowered)
        is not None
        or re.search(r"\bi\s+can\s+read\b.{0,120}\b(?:would\s+you\s+like|want)\b", lowered)
        is not None
    )


def _assistant_requests_file_path_for_text_read(text: str) -> bool:
    lowered = " ".join(str(text).casefold().split())
    return (
        re.search(r"\b(?:full|exact)\s+path\b", lowered) is not None
        and re.search(r"\b(?:read|file|drive\s+letter|directory\s+structure)\b", lowered)
        is not None
    )


def _multiple_file_candidates_answer(
    requested_name: str,
    directory: str,
    candidates: tuple[str, ...],
) -> str:
    lines = [f"Multiple possible files match {requested_name} in {directory}. Choose one exact filename:"]
    lines.extend(f"- {_safe_text(str(candidate))}" for candidate in candidates)
    return "\n".join(lines)


def _is_affirmative(lowered: str) -> re.Match[str] | None:
    return re.fullmatch(
        r"(?:yes|yep|yeah|sure|ok|okay|please|please\s+do|do\s+it|proceed)",
        lowered,
    )


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(right)
    )


def _observed_required_calls_complete(
    required_calls: tuple[ModelCapabilityCall, ...],
    observed_results: list[tuple],
) -> bool:
    pending = list(required_calls)
    for observed_call, _result in observed_results:
        for index, required in enumerate(pending):
            if _same_capability_call(observed_call, required):
                pending.pop(index)
                break
    return not pending


def _same_capability_call(left: ModelCapabilityCall, right: ModelCapabilityCall) -> bool:
    return left.capability == right.capability and left.arguments == right.arguments


def _grounded_text_read_answer(
    user_text: str,
    assistant_text: str,
    observed_results: list[tuple],
) -> str | None:
    call_and_result = _latest_successful_text_read(observed_results)
    if call_and_result is None:
        return None
    _call, result = call_and_result
    output = result.output or {}
    file_text = output.get("text")
    if not isinstance(file_text, str):
        return None
    if not _should_ground_text_read_answer(user_text, assistant_text, file_text):
        return None
    return _render_text_result((call_and_result[0],), [call_and_result])


def _latest_successful_text_read(observed_results: list[tuple]) -> tuple | None:
    for call, result in reversed(observed_results):
        if call.capability != "filesystem.read_text" or not result.success:
            continue
        output = result.output or {}
        if isinstance(output.get("text"), str):
            return call, result
    return None


def _should_ground_text_read_answer(
    user_text: str,
    assistant_text: str,
    file_text: str,
) -> bool:
    lowered_answer = " ".join(str(assistant_text).casefold().split())
    if re.search(
        r"\b(?:cannot|can't|can\s+not)\s+show\s+the\s+full\s+content\b",
        lowered_answer,
    ):
        return True
    if re.search(r"\bcapability restrictions?\b", lowered_answer):
        return True
    if file_text and file_text in assistant_text:
        return False
    return _is_direct_content_read_request(user_text)


def _is_direct_content_read_request(text: str) -> bool:
    lowered = " ".join(str(text).casefold().split())
    if re.search(
        r"\b(?:summari[sz]e|summary|analy[sz]e|explain|review|classify|compare|extract|parse)\b",
        lowered,
    ):
        return False
    if re.match(
        r"(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:read|show|display|print|paste|open)\b",
        lowered,
    ):
        return True
    if re.search(
        r"\b(?:read|show|display|print|paste)\b.{0,120}\b(?:contents?|content|file|it|this|that)\b",
        lowered,
    ):
        return True
    return re.search(r"\bwhat\s+does\s+(?:it|this|that|the\s+file)\s+say\b", lowered) is not None


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
        or re.search(r"\bwhat(?:'s|\s+is)\s+(?:in|inside)\s+(?:it|there|that|this)\b", lowered)
        or re.search(
            r"\bwhat\s+(?:files?|folders?|directories|entries|items)\s+"
            r"(?:i|we)\s+have\s+(?:there|in\s+it|inside\s+it)\b",
            lowered,
        )
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
