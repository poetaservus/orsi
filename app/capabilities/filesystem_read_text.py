from __future__ import annotations

import codecs
import hashlib
import stat
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    ExecutionIsolation,
    PermissionClass,
)
from app.security.host_access import HostReadScope
from app.security.path_policy import resolve_candidate_path, resolve_read_path


DEFAULT_MAX_BYTES = 16 * 1024
MAX_TEXT_BYTES = 64 * 1024
DEFAULT_MAX_LINES = 200
MAX_TEXT_LINES = 1_000
TextEncoding = Literal["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"]
_TEXT_CONTROL_CHARACTERS = {"\t", "\n", "\r", "\f"}


class FilesystemReadTextArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(
        min_length=1,
        max_length=32_767,
        description=(
            "Copy the requested text-file path exactly. Absolute paths must preserve their drive "
            "letter, directories, separators, spelling, and capitalization. A relative path is "
            "already relative to the active read scope's documented root, so do not invent or "
            "prefix directories."
        ),
    )
    encoding: TextEncoding = Field(
        default="utf-8",
        description=(
            "Text decoding to apply. Use utf-8 unless the user explicitly identifies one of the "
            "supported UTF encodings."
        ),
    )
    max_bytes: int = Field(
        default=DEFAULT_MAX_BYTES,
        ge=1,
        le=MAX_TEXT_BYTES,
        description="Maximum bytes to read, from 1 through 65,536 inclusive.",
    )
    max_lines: int = Field(
        default=DEFAULT_MAX_LINES,
        ge=1,
        le=MAX_TEXT_LINES,
        description="Maximum decoded text lines to return, from 1 through 1,000 inclusive.",
    )


class FilesystemReadTextCapability(Capability[FilesystemReadTextArguments]):
    name = "filesystem.read_text"
    description = (
        "Return a bounded excerpt from one allowed UTF text file with binary rejection and "
        "explicit source completeness. Before editing text missing from a truncated result, "
        "read the same path and encoding with max_bytes=65536 and max_lines=1000. "
        "Use only exact source actually returned; if the target is still missing, report the "
        "read limitation instead of guessing a patch."
    )
    arguments_model = FilesystemReadTextArguments
    permission = PermissionClass.READ
    timeout_seconds = 3.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def permission_resource(
        self,
        arguments: FilesystemReadTextArguments,
        context: CapabilityContext,
    ) -> Path:
        policy = context.host_access_policy
        if policy is not None and policy.read_scope == HostReadScope.FULL_LOCAL:
            return policy.resolve_read(arguments.path).resolved
        return resolve_candidate_path(
            arguments.path,
            portable_root=context.portable_root,
        ).resolved

    def execute(
        self,
        arguments: FilesystemReadTextArguments,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        if context.host_access_policy is not None:
            resolved = context.host_access_policy.resolve_read(arguments.path)
        else:
            resolved = resolve_read_path(
                arguments.path,
                portable_root=context.portable_root,
                allowed_roots=context.allowed_read_roots,
            )
        context.cancellation.raise_if_cancelled()
        total_size = _require_regular_file(resolved.requested, resolved.resolved)
        raw, truncated_by_bytes = _read_bounded_bytes(
            resolved.resolved,
            arguments.max_bytes,
            context,
        )
        context.cancellation.raise_if_cancelled()
        text = _decode_text(
            raw,
            arguments.encoding,
            truncated_by_bytes=truncated_by_bytes,
        )
        text, lines_returned, truncated_by_lines = _apply_line_limit(
            text,
            arguments.max_lines,
        )
        source_complete = not (truncated_by_bytes or truncated_by_lines)
        read_hint = None
        if not source_complete:
            can_expand = (
                truncated_by_bytes and arguments.max_bytes < MAX_TEXT_BYTES
            ) or (
                truncated_by_lines and arguments.max_lines < MAX_TEXT_LINES
            )
            if can_expand:
                read_hint = (
                    "Source is truncated. Read the same path and encoding with "
                    "max_bytes=65536 and max_lines=1000 before editing text missing here. "
                    "Repeating this truncated prefix cannot reveal the missing target."
                )
            else:
                read_hint = (
                    "Source is truncated at the supported 65,536-byte / 1,000-line limit. "
                    "If the requested target is missing, stop and request a smaller source "
                    "file containing it; this tool does not support range reads."
                )
            read_hint += (
                " Use only exact text present in returned source. Do not invent unseen "
                "source or an unavailable whole-file digest."
            )
        context.cancellation.raise_if_cancelled()
        return {
            "path": str(resolved.resolved),
            "encoding": arguments.encoding,
            "text": text,
            "bytes_read": len(raw),
            "total_size_bytes": total_size,
            "lines_returned": lines_returned,
            "truncated_by_bytes": truncated_by_bytes,
            "truncated_by_lines": truncated_by_lines,
            "source_complete": source_complete,
            "read_hint": read_hint,
            "content_is_untrusted": True,
            # This hashes actual complete bytes, never an excerpt. A line-limited
            # read may have a revision digest without returning the complete text.
            "sha256": hashlib.sha256(raw).hexdigest() if not truncated_by_bytes else None,
        }


def _require_regular_file(requested: Path, resolved: Path) -> int:
    try:
        requested.lstat()
        target_stat = resolved.stat()
    except FileNotFoundError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested text file does not exist.",
        ) from exc
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested text file is not accessible.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested text file could not be inspected.",
        ) from exc
    if not stat.S_ISREG(target_stat.st_mode):
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested path is not a regular text file.",
        )
    return int(target_stat.st_size)


def _read_bounded_bytes(
    path: Path,
    max_bytes: int,
    context: CapabilityContext,
) -> tuple[bytes, bool]:
    context.cancellation.raise_if_cancelled()
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested text file is not readable.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested text file read failed.",
        ) from exc
    truncated = len(raw) > max_bytes
    return (raw[:max_bytes], truncated) if truncated else (raw, False)


def _decode_text(
    raw: bytes,
    encoding: TextEncoding,
    *,
    truncated_by_bytes: bool,
) -> str:
    if encoding in {"utf-8", "utf-8-sig"} and b"\x00" in raw:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested file appears to be binary, not text.",
        )
    try:
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        text = decoder.decode(raw, final=not truncated_by_bytes)
    except (LookupError, UnicodeError) as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested file is not valid text for the selected encoding.",
        ) from exc
    if _contains_binary_control_text(text):
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested file appears to be binary, not text.",
        )
    return text


def _contains_binary_control_text(text: str) -> bool:
    return any(
        (character not in _TEXT_CONTROL_CHARACTERS and ord(character) < 32)
        or ord(character) == 127
        for character in text
    )


def _apply_line_limit(text: str, max_lines: int) -> tuple[str, int, bool]:
    if not text:
        return "", 0, False
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text, len(lines), False
    return "".join(lines[:max_lines]), max_lines, True
