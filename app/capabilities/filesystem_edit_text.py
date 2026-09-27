from __future__ import annotations

import codecs
import hashlib
import json
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (
    Capability, CapabilityErrorCode, CapabilityExecutionError,
    ExecutionIsolation, PermissionClass,
)
from app.capabilities.filesystem_read_text import _contains_binary_control_text
from app.capabilities.filesystem_write_text import atomic_write_text_file
from app.execution.windows_filesystem import pinned_parent, read_file_snapshot
from app.security.write_policy import HostWritePolicy


MAX_FILE_BYTES = 1_048_576
MAX_FILE_LINES = 10_000
MAX_PREVIEW_CHARS = 32_768
MAX_FRAGMENT_CHARS = 16_384


class FilesystemEditTextArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1, max_length=32767,
                      description="Exact absolute local-drive path of an existing UTF-8 file. Copy the path returned by the source read; never shorten it to a filename.")
    old_text: str = Field(min_length=1, max_length=MAX_FRAGMENT_CHARS,
                         description="A unique exact excerpt from the source read, including original line endings and enough surrounding text to identify the requested location. For one CSS rule include its selector, not a declaration repeated in other rules. No fuzzy matching.")
    new_text: str = Field(max_length=MAX_FRAGMENT_CHARS,
                         description="Replacement for the entire old_text excerpt. Copy old_text and change only the requested content; retain every unchanged selector, declaration, closing brace, and line ending. Example: old_text='header { color: red; }', new_text='header { color: white; }'.")
    replace_all: bool = Field(default=False,
                              description="Replace every non-overlapping match only when explicitly requested.")
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
                                        description="SHA-256 of the complete source bytes from a preceding read, when available. Never use an excerpt digest.")


@dataclass(frozen=True)
class EditPlan:
    data: bytes
    preview: str
    replacements: int
    additions: int
    deletions: int


class FilesystemEditTextCapability(Capability[FilesystemEditTextArguments]):
    name = "filesystem.edit_text"
    description = "Replace exact text in one existing UTF-8 file after approval of a complete diff; prefer this for small edits."
    arguments_model = FilesystemEditTextArguments
    permission = PermissionClass.WRITE
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE
    timeout_seconds = 3.0

    def __init__(self, policy: HostWritePolicy):
        if not isinstance(policy, HostWritePolicy):
            raise TypeError("Text editing requires a separate HostWritePolicy.")
        self.policy = policy

    def permission_resource(self, arguments, context) -> Path:
        context.cancellation.raise_if_cancelled()
        return self.policy.resolve_text_file(arguments.path)

    def approval_details(self, arguments, context):
        path = self.permission_resource(arguments, context)
        try:
            with pinned_parent(path, context.cancellation) as (_, parent):
                raw, identity = _snapshot(path, context.cancellation)
                plan = plan_edit(raw, arguments)
                return plan.preview, _binding(parent, identity, raw)
        except OSError as exc:
            _path_error(exc)

    def execute(self, arguments, context) -> dict:
        path = self.permission_resource(arguments, context)
        if (context.authorized_resource != str(path)
                or context.authorized_resource_identity is None):
            raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                                           "Text editing requires exact runtime authorization.")
        try:
            with pinned_parent(path, context.cancellation) as (_, parent):
                def checked_snapshot():
                    raw, identity = _snapshot(path, context.cancellation)
                    if _binding(parent, identity, raw) != context.authorized_resource_identity:
                        raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                            "The target file changed after the preview. Request a new approval.")
                    return raw

                raw = checked_snapshot()
                plan = plan_edit(raw, arguments)
                context.cancellation.raise_if_cancelled()
                identity = atomic_write_text_file(path, plan.data, context.cancellation,
                                                  before_replace=checked_snapshot)
                # All failures after replacement are unknown outcomes, never safe-to-retry errors.
                try:
                    final, final_identity = _snapshot(path, context.cancellation)
                    if final != plan.data or final_identity != identity:
                        raise RuntimeError("Edited file verification failed.")
                except Exception as exc:
                    raise RuntimeError("The edited file could not be verified.") from exc
                return {"path": str(path), "replacements": plan.replacements,
                        "additions": plan.additions, "deletions": plan.deletions,
                        "sha256": hashlib.sha256(plan.data).hexdigest()}
        except OSError as exc:
            _path_error(exc)


def _binding(parent: str, identity: str, raw: bytes) -> str:
    return f"{parent}|file:{identity}|sha256:{hashlib.sha256(raw).hexdigest()}"


def _snapshot(path, cancellation):
    try:
        return read_file_snapshot(path, MAX_FILE_BYTES, cancellation)
    except ValueError as exc:
        raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS,
                                       "Text edits are limited to 1 MiB files.") from exc


def _invalid(message):
    raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS, message)


def plan_edit(raw: bytes, arguments: FilesystemEditTextArguments) -> EditPlan:
    if len(raw) > MAX_FILE_BYTES:
        _invalid("Text edits are limited to 1 MiB files.")
    if (arguments.expected_sha256 is not None
            and hashlib.sha256(raw).hexdigest() != arguments.expected_sha256):
        _invalid("The source digest does not match the expected SHA-256. Read the file again.")
    bom = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
    try:
        text = raw[len(bom):].decode("utf-8", errors="strict")
        arguments.old_text.encode("utf-8", errors="strict")
        arguments.new_text.encode("utf-8", errors="strict")
    except UnicodeError:
        _invalid("Text edits require valid UTF-8 text.")
    if any(_contains_binary_control_text(value)
           for value in (text, arguments.old_text, arguments.new_text)):
        _invalid("Binary control characters are not supported by text editing.")
    # Count overlapping matches too: never silently choose one of two competing spans.
    positions = []
    start = 0
    while True:
        index = text.find(arguments.old_text, start)
        if index < 0:
            break
        if positions and index < positions[-1] + len(arguments.old_text):
            _invalid("The search text has overlapping matches. Use a more specific excerpt.")
        positions.append(index)
        if len(positions) > 1 and not arguments.replace_all:
            _invalid("The search text has multiple matches; no edit was made. Expand old_text with "
                     "exact surrounding lines from the source read to identify the requested location "
                     "(for CSS, include the selector). Retain those lines in new_text and submit the "
                     "corrected edit. Do not repeat the same call or use replace_all unless the user "
                     "requested every occurrence.")
        start = index + 1
    if not positions:
        _invalid("The exact search text was not found. Read the file again.")
    if arguments.old_text == arguments.new_text:
        _invalid("The requested edit makes no change.")
    # Bound expansion before allocating the result.
    result_size = len(raw) + len(positions) * (
        len(arguments.new_text.encode("utf-8")) - len(arguments.old_text.encode("utf-8")))
    if result_size > MAX_FILE_BYTES:
        _invalid("The edited file would exceed 1 MiB.")
    updated = text.replace(arguments.old_text, arguments.new_text)
    before, after = text.splitlines(keepends=True), updated.splitlines(keepends=True)
    if max(len(before), len(after)) > MAX_FILE_LINES:
        _invalid("Text edits are limited to 10,000 lines.")
    preview = ["Exact diff; each line is JSON-escaped (\\r, \\n, tabs and Unicode are explicit).\n"]
    size, additions, deletions = len(preview[0]), 0, 0
    # Escape each complete diff line, preserving even missing final newlines.
    for index, line in enumerate(unified_diff(before, after, fromfile="before", tofile="after", n=3)):
        rendered = json.dumps(line, ensure_ascii=True) + "\n"
        size += len(rendered)
        if size > MAX_PREVIEW_CHARS:
            _invalid("The complete edit diff exceeds the approval limit. Request a smaller edit.")
        preview.append(rendered)
        if index > 1 and line.startswith("+"):
            additions += 1
        if index > 1 and line.startswith("-"):
            deletions += 1
    return EditPlan(bom + updated.encode("utf-8"), "".join(preview), len(positions), additions, deletions)


def _path_error(exc):
    if isinstance(exc, FileNotFoundError):
        code, message = CapabilityErrorCode.NOT_FOUND, "The existing text file or its parent does not exist."
    else:
        code, message = CapabilityErrorCode.INACCESSIBLE, "The text file is protected, redirected, or unavailable."
    raise CapabilityExecutionError(code, message) from exc
