from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import (
    Capability,
    CapabilityContext,
    CapabilityErrorCode,
    CapabilityExecutionError,
    ExecutionIsolation,
    PermissionClass,
)
from app.capabilities.host_access import HostReadScope
from app.capabilities.path_policy import resolve_candidate_path, resolve_read_path


DEFAULT_MAX_DEPTH = 3
MAX_SEARCH_DEPTH = 8
DEFAULT_MAX_FILES = 256
MAX_SEARCH_FILES = 1_024
MAX_SEARCH_ENTRIES = 4_096
DEFAULT_MAX_FILE_BYTES = 16 * 1024
MAX_SEARCH_FILE_BYTES = 64 * 1024
DEFAULT_MAX_MATCHES = 25
MAX_SEARCH_MATCHES = 100
DEFAULT_SNIPPET_CHARS = 160
MAX_SNIPPET_CHARS = 300
_TEXT_CONTROL_CHARACTERS = {"\t", "\n", "\r", "\f"}


class FilesystemSearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(
        min_length=1,
        max_length=32_767,
        description=(
            "Copy the requested directory path exactly. Absolute paths must preserve their drive "
            "letter, directories, separators, spelling, and capitalization. A relative path is "
            "already relative to the active read scope's documented root, so do not invent or "
            "prefix directories."
        ),
    )
    query: str = Field(
        min_length=1,
        max_length=512,
        description=(
            "Literal text to search for inside UTF text files. Copy only the user's requested "
            "search text; do not transform it into a regular expression."
        ),
    )
    case_sensitive: bool = Field(
        default=False,
        description="Whether matching should preserve case. Default is case-insensitive literal search.",
    )
    max_depth: int = Field(
        default=DEFAULT_MAX_DEPTH,
        ge=0,
        le=MAX_SEARCH_DEPTH,
        description="Maximum directory depth to search, from 0 through 8 inclusive.",
    )
    max_files: int = Field(
        default=DEFAULT_MAX_FILES,
        ge=1,
        le=MAX_SEARCH_FILES,
        description="Maximum regular files to inspect, from 1 through 1,024 inclusive.",
    )
    max_file_bytes: int = Field(
        default=DEFAULT_MAX_FILE_BYTES,
        ge=1,
        le=MAX_SEARCH_FILE_BYTES,
        description="Maximum bytes to read from each file, from 1 through 65,536 inclusive.",
    )
    max_matches: int = Field(
        default=DEFAULT_MAX_MATCHES,
        ge=1,
        le=MAX_SEARCH_MATCHES,
        description="Maximum returned matches, from 1 through 100 inclusive.",
    )
    snippet_chars: int = Field(
        default=DEFAULT_SNIPPET_CHARS,
        ge=40,
        le=MAX_SNIPPET_CHARS,
        description="Maximum characters to include in each matching line snippet.",
    )


@dataclass(slots=True)
class _SearchCounters:
    entries_scanned: int = 0
    directories_scanned: int = 0
    files_scanned: int = 0
    skipped_files: int = 0
    truncated_files: int = 0


class FilesystemSearchCapability(Capability[FilesystemSearchArguments]):
    name = "filesystem.search"
    description = "Search bounded UTF text snippets under one allowed directory."
    arguments_model = FilesystemSearchArguments
    permission = PermissionClass.READ
    timeout_seconds = 5.0
    execution_isolation = ExecutionIsolation.IN_PROCESS_COOPERATIVE

    def permission_resource(
        self,
        arguments: FilesystemSearchArguments,
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
        arguments: FilesystemSearchArguments,
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
        _require_directory(resolved.requested, resolved.resolved)
        counters = _SearchCounters()
        matches: list[dict[str, Any]] = []
        needle = arguments.query if arguments.case_sensitive else arguments.query.casefold()

        for file_path in _iter_regular_files(
            resolved.resolved,
            max_depth=arguments.max_depth,
            max_files=arguments.max_files,
            counters=counters,
            context=context,
        ):
            text, truncated = _read_search_text(
                file_path,
                max_bytes=arguments.max_file_bytes,
                context=context,
            )
            if text is None:
                counters.skipped_files += 1
                continue
            if truncated:
                counters.truncated_files += 1
            haystack_lines = text.splitlines()
            for line_number, line in enumerate(haystack_lines, start=1):
                comparison = line if arguments.case_sensitive else line.casefold()
                match_index = comparison.find(needle)
                if match_index < 0:
                    continue
                matches.append(
                    {
                        "path": str(file_path),
                        "relative_path": _relative_path(file_path, resolved.resolved),
                        "line_number": line_number,
                        "snippet": _snippet(
                            line,
                            match_index=match_index,
                            query_length=len(arguments.query),
                            width=arguments.snippet_chars,
                        ),
                        "file_truncated": truncated,
                    }
                )
                if len(matches) >= arguments.max_matches:
                    return _search_output(
                        resolved.resolved,
                        arguments,
                        counters,
                        matches,
                        truncated_by_matches=True,
                    )
            context.cancellation.raise_if_cancelled()

        return _search_output(
            resolved.resolved,
            arguments,
            counters,
            matches,
            truncated_by_matches=False,
        )


def _require_directory(requested: Path, resolved: Path) -> None:
    try:
        requested.lstat()
        target_stat = resolved.stat()
    except FileNotFoundError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.NOT_FOUND,
            "The requested search directory does not exist.",
        ) from exc
    except PermissionError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested search directory is not accessible.",
        ) from exc
    except OSError as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The requested search directory could not be inspected.",
        ) from exc
    if not stat.S_ISDIR(target_stat.st_mode):
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The requested search path is not a directory.",
        )


def _iter_regular_files(
    root: Path,
    *,
    max_depth: int,
    max_files: int,
    counters: _SearchCounters,
    context: CapabilityContext,
):
    pending: list[tuple[Path, int]] = [(root, 0)]
    while pending:
        directory, depth = pending.pop(0)
        context.cancellation.raise_if_cancelled()
        counters.directories_scanned += 1
        try:
            with os.scandir(directory) as iterator:
                entries = list(iterator)
        except FileNotFoundError as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.NOT_FOUND,
                "A searched directory no longer exists.",
            ) from exc
        except PermissionError:
            continue
        except OSError as exc:
            raise CapabilityExecutionError(
                CapabilityErrorCode.INACCESSIBLE,
                "The search directory scan failed.",
            ) from exc

        entries.sort(key=lambda item: (item.name.casefold(), item.name))
        for item in entries:
            context.cancellation.raise_if_cancelled()
            counters.entries_scanned += 1
            if counters.entries_scanned > MAX_SEARCH_ENTRIES:
                raise CapabilityExecutionError(
                    CapabilityErrorCode.OUTPUT_LIMITED,
                    f"The directory exceeds the bounded {MAX_SEARCH_ENTRIES:,}-entry search limit.",
                )
            try:
                item_stat = item.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            except (PermissionError, OSError):
                counters.skipped_files += 1
                continue
            if _is_reparse_or_symlink(item, item_stat):
                continue
            if stat.S_ISDIR(item_stat.st_mode):
                if depth < max_depth:
                    pending.append((Path(item.path), depth + 1))
                continue
            if not stat.S_ISREG(item_stat.st_mode):
                continue
            counters.files_scanned += 1
            if counters.files_scanned > max_files:
                raise CapabilityExecutionError(
                    CapabilityErrorCode.OUTPUT_LIMITED,
                    f"The directory exceeds the bounded {max_files:,}-file search limit.",
                )
            yield Path(item.path)


def _is_reparse_or_symlink(item: os.DirEntry[str], item_stat: os.stat_result) -> bool:
    attributes = int(getattr(item_stat, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    if reparse_flag and attributes & reparse_flag:
        return True
    try:
        return stat.S_ISLNK(item_stat.st_mode) or item.is_symlink()
    except OSError:
        return stat.S_ISLNK(item_stat.st_mode)


def _read_search_text(
    path: Path,
    *,
    max_bytes: int,
    context: CapabilityContext,
) -> tuple[str | None, bool]:
    context.cancellation.raise_if_cancelled()
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except (PermissionError, OSError):
        return None, False
    truncated = len(raw) > max_bytes
    payload = raw[:max_bytes] if truncated else raw
    if b"\x00" in payload:
        return None, truncated
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        return None, truncated
    if _contains_binary_control_text(text):
        return None, truncated
    return text, truncated


def _contains_binary_control_text(text: str) -> bool:
    return any(
        (character not in _TEXT_CONTROL_CHARACTERS and ord(character) < 32)
        or ord(character) == 127
        for character in text
    )


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _snippet(line: str, *, match_index: int, query_length: int, width: int) -> str:
    text = line.strip("\r\n")
    if len(text) <= width:
        return text
    query_length = max(1, query_length)
    context = max(0, (width - query_length) // 2)
    start = max(0, match_index - context)
    end = min(len(text), match_index + query_length + context)
    if end - start < width and start > 0:
        start = max(0, end - width)
    if end - start < width and end < len(text):
        end = min(len(text), start + width)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _search_output(
    root: Path,
    arguments: FilesystemSearchArguments,
    counters: _SearchCounters,
    matches: list[dict[str, Any]],
    *,
    truncated_by_matches: bool,
) -> dict[str, Any]:
    return {
        "path": str(root),
        "query": arguments.query,
        "case_sensitive": arguments.case_sensitive,
        "matches": matches,
        "returned_matches": len(matches),
        "max_matches": arguments.max_matches,
        "truncated_by_matches": truncated_by_matches,
        "files_scanned": counters.files_scanned,
        "directories_scanned": counters.directories_scanned,
        "entries_scanned": counters.entries_scanned,
        "skipped_files": counters.skipped_files,
        "truncated_files": counters.truncated_files,
        "max_depth": arguments.max_depth,
        "max_file_bytes": arguments.max_file_bytes,
        "content_is_untrusted": True,
    }
