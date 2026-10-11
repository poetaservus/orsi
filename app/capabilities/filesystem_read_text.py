from __future__ import annotations

import codecs
import hashlib
import json
import stat
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
MAX_PAGE_JSON_TEXT_BYTES = 40 * 1024
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
    offset: int = Field(default=0, ge=0, description="Byte offset from next_read, starting at zero. Never guess offsets inside encoded characters.")
    expected_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
        description="Revision from the previous page; required for continuation. A changed file requires restarting at offset zero.")

    @model_validator(mode="after")
    def continuation_requires_revision(self):
        if self.offset and self.expected_revision is None:
            raise ValueError("Continuation requires the previous page revision.")
        return self


class FilesystemReadTextCapability(Capability[FilesystemReadTextArguments]):
    name = "filesystem.read_text"
    description = (
        "Read a contiguous bounded page of an allowed UTF text file. Follow next_read to reach "
        "later source; larger pages use max_bytes=65536 and max_lines=1000. Follow next_read "
        "retaining its expected_revision; restart if the file changes. Use only "
        "exact returned source for edits. source_complete means the entire file, not just a page."
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
        revision = _revision(resolved.resolved)
        if arguments.expected_revision is not None and arguments.expected_revision != revision:
            raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS,
                "The source revision changed. Restart the read at offset zero without expected_revision.")
        if arguments.offset > total_size:
            raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS, "The read offset exceeds the file size.")
        if arguments.offset == 0:
            raw, truncated_by_bytes = _read_bounded_bytes(resolved.resolved, arguments.max_bytes, context)
        else:
            try:
                with resolved.resolved.open("rb") as handle:
                    handle.seek(arguments.offset)
                    page = handle.read(arguments.max_bytes + 1)
            except OSError as exc:
                raise CapabilityExecutionError(CapabilityErrorCode.INACCESSIBLE, "The requested source page is no longer readable.") from exc
            raw, truncated_by_bytes = page[:arguments.max_bytes], len(page) > arguments.max_bytes
        if _revision(resolved.resolved) != revision:
            raise CapabilityExecutionError(CapabilityErrorCode.INACCESSIBLE, "The source changed during the read. Restart at offset zero.")
        context.cancellation.raise_if_cancelled()
        codec, bom_bytes = page_codec(resolved.resolved, arguments.encoding, arguments.offset, raw)
        if codec.startswith("utf-16") and arguments.offset % 2:
            raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS, "UTF-16 continuation offsets must be at a code-unit boundary.")
        partial_bom = bom_bytes > len(raw)
        if partial_bom:
            bom_bytes = 0
        text = _decode_text(
            b"" if partial_bom else raw[bom_bytes:],
            codec,
            truncated_by_bytes=truncated_by_bytes,
        )
        text, lines_returned, truncated_by_lines = _apply_line_limit(
            text,
            arguments.max_lines,
        )
        text, truncated_by_output = _bound_page_text(text)
        if truncated_by_output:
            lines_returned = len(text.splitlines())
        consumed = bom_bytes + len(text.encode(codec))
        end = arguments.offset + consumed
        has_more = end < total_size
        source_complete = arguments.offset == 0 and not has_more
        read_hint = None
        if has_more:
            read_hint = ("Follow next_read for the next contiguous page. Repeating this prefix cannot reveal later source. "
                "For a larger page use max_bytes=65536 and max_lines=1000. Use only exact returned text; "
                "the revision token is a file identity precondition, not a whole-file content digest.")
        context.cancellation.raise_if_cancelled()
        if _revision(resolved.resolved) != revision:
            raise CapabilityExecutionError(CapabilityErrorCode.INACCESSIBLE, "The source changed during decoding. Restart at offset zero.")
        return {
            "path": str(resolved.resolved),
            "encoding": arguments.encoding,
            "text": text,
            "bytes_read": len(raw),
            "total_size_bytes": total_size,
            "lines_returned": lines_returned,
            "truncated_by_bytes": truncated_by_bytes,
            "truncated_by_lines": truncated_by_lines,
            "truncated_by_output": truncated_by_output,
            "source_complete": source_complete,
            "read_hint": read_hint,
            "content_is_untrusted": True,
            "offset": arguments.offset,
            "text_offset": arguments.offset + bom_bytes,
            "end_offset": end,
            "bytes_returned": consumed,
            "page_encoding": codec,
            "revision": revision,
            "has_more": has_more,
            "next_offset": end if has_more else None,
            "next_read": {"path": arguments.path, "encoding": arguments.encoding,
                "offset": end, "expected_revision": revision, "max_bytes": max(4, arguments.max_bytes) if consumed == 0 else arguments.max_bytes,
                "max_lines": arguments.max_lines} if has_more else None,
            # This hashes actual complete bytes, never an excerpt. A line-limited
            # read may have a revision digest without returning the complete text.
            "sha256": hashlib.sha256(raw).hexdigest() if arguments.offset == 0 and not truncated_by_bytes else None,
        }


def _bound_page_text(text: str) -> tuple[str, bool]:
    """Leave room for structured continuation inside the executor's 64-KiB result."""
    def size(value: str) -> int:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    if size(text) <= MAX_PAGE_JSON_TEXT_BYTES:
        return text, False
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if size(text[:middle]) <= MAX_PAGE_JSON_TEXT_BYTES:
            low = middle
        else:
            high = middle - 1
    return text[:low], True


def _revision(path: Path) -> str:
    try:
        value = path.stat()
    except OSError as exc:
        raise CapabilityExecutionError(CapabilityErrorCode.INACCESSIBLE,
            "The source revision is no longer accessible. Restart from a fresh file read.") from exc
    return hashlib.sha256(json.dumps((value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)).encode("ascii")).hexdigest()


def page_codec(path: Path, encoding: str, offset: int, raw: bytes) -> tuple[str, int]:
    """Use a BOM only at byte zero; continuation uses the same concrete codec."""
    if encoding == "utf-16":
        with path.open("rb") as handle:
            bom = handle.read(2)
        if bom not in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
            raise CapabilityExecutionError(CapabilityErrorCode.INVALID_ARGUMENTS, "UTF-16 requires a byte order mark.")
        return ("utf-16-le" if bom == codecs.BOM_UTF16_LE else "utf-16-be", 2 if offset == 0 else 0)
    if encoding == "utf-8-sig":
        return "utf-8", 3 if offset == 0 and raw.startswith(codecs.BOM_UTF8) else 0
    return encoding, 0


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
