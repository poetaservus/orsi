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
                    call.capability == "filesystem.list" for call in required_calls
                ):
                    answer = _render_listing_results(required_calls, turn_results)
                completed_capabilities = {
                    call.capability for call, _result in turn_results
                }
                if "filesystem.stat" in completed_capabilities:
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
                    self.agent_capabilities,
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
        if "filesystem.list" in available and re.search(
            r"\bfilesystem[.]list\b", lowered
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
                r"(?:files?|folders?|director(?:y|ies)|entries|contents)\b",
                lowered,
            ):
                return True
            if re.search(r"\b(?:what|which)\s+(?:files?|folders?|directories|entries)\b", lowered):
                return True
            if re.search(
                r"\b(?:files?|folders?|directories|entries)\s+"
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
            r"(?:files?|folders?|director(?:y|ies)|entries|contents)\b",
            lowered,
        )
        or re.search(r"\b(?:what|which)\s+(?:files?|folders?|directories|entries)\b", lowered)
        or re.search(
            r"\b(?:files?|folders?|directories|entries)\s+"
            r"(?:do\s+i\s+have|are\s+(?:in|inside|under|there))\b",
            lowered,
        )
        or re.search(r"\b(?:contents|entries)\s+(?:of|in|inside)\b", lowered)
        or re.search(r"\b(?:show\s+me\s+)?what\s+is\s+in\b", lowered)
    )
