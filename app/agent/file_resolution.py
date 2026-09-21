from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from app.capabilities.contracts import CapabilityErrorCode


_FEEDBACK_MARKER = "Bounded filename disambiguation is still pending."


@dataclass(frozen=True)
class _PendingFilenameDisambiguation:
    directory: str
    requested_name: str
    source_capability: str


def filename_disambiguation_feedback(
    transcript: list[dict[str, Any]],
    advertised_names: set[str],
) -> dict[str, str] | None:
    """Request one bounded same-directory recovery step for extensionless reads."""
    if not {"filesystem.list", "filesystem.read_text"}.issubset(advertised_names):
        return None
    if _feedback_already_sent(transcript):
        return None
    latest_user = _latest_user_text(transcript).casefold()
    if re.search(r"\b(?:read|show|explain|summari[sz]e|fix)\b", latest_user) is None:
        return None
    pending = _pending_disambiguation(transcript)
    if pending is None:
        return None
    directory = pending.directory
    requested_name = pending.requested_name
    last_result = _last_capability_result(transcript)
    if last_result is None:
        return None
    capability = last_result.get("capability")
    output = last_result.get("result", {}).get("output", {})
    if capability == "filesystem.find":
        if _has_following_result(transcript, "filesystem.list", directory):
            return None
        return {
            "role": "system",
            "content": (
                f"{_FEEDBACK_MARKER} The exact file lookup returned no matches. "
                "Return exactly one native filesystem.list call for the same containing "
                f"directory: {directory}. Do not answer that the file is missing until this "
                "bounded same-folder disambiguation has run. Do not search another folder."
            ),
        }
    if capability == "filesystem.read_text" and pending.source_capability == "filesystem.read_text":
        if _has_following_result(transcript, "filesystem.list", directory):
            return None
        return {
            "role": "system",
            "content": (
                f"{_FEEDBACK_MARKER} The direct text read failed for an extensionless path. "
                "Return exactly one native filesystem.list call for the same containing "
                f"directory: {directory}. Do not answer that the file is missing until this "
                "bounded same-folder disambiguation has run. Do not search another folder."
            ),
        }
    if capability == "filesystem.list" and _result_matches_directory(
        transcript,
        last_result,
        "filesystem.list",
        directory,
    ):
        if _has_following_result(transcript, "filesystem.read_text", directory):
            return None
        candidates = _matching_files(requested_name, list(output.get("entries") or []))
        if len(candidates) != 1:
            return None
        read_directory = output.get("path") if isinstance(output.get("path"), str) else directory
        return {
            "role": "system",
            "content": (
                f"{_FEEDBACK_MARKER} The same-folder list has exactly one obvious file match "
                f"for {requested_name}: {candidates[0]}. Return exactly one native "
                f"filesystem.read_text call for {str(Path(read_directory) / candidates[0])}. "
                "Do not return assistant text before reading it."
            ),
        }
    return None


def _feedback_already_sent(transcript: list[dict[str, Any]]) -> bool:
    last_result_index = None
    for index, message in enumerate(transcript):
        if message.get("role") == "capability":
            last_result_index = index
    if last_result_index is None:
        return False
    return any(
        index > last_result_index
        and message.get("role") == "system"
        and isinstance(message.get("content"), str)
        and _FEEDBACK_MARKER in message["content"]
        for index, message in enumerate(transcript)
    )


def _latest_user_text(transcript: list[dict[str, Any]]) -> str:
    for message in reversed(transcript):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _last_capability_result(transcript: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (message for message in reversed(transcript) if message.get("role") == "capability"),
        None,
    )


def _pending_disambiguation(
    transcript: list[dict[str, Any]],
) -> _PendingFilenameDisambiguation | None:
    for message in reversed(transcript):
        pending = _pending_from_result(transcript, message)
        if pending is not None:
            return pending
    return None


def _pending_from_result(
    transcript: list[dict[str, Any]],
    message: dict[str, Any],
) -> _PendingFilenameDisambiguation | None:
    if message.get("role") != "capability":
        return None
    result = message.get("result") or {}
    output = result.get("output") or {}
    capability = message.get("capability")
    if (
        capability == "filesystem.find"
        and result.get("success") is True
        and output.get("kind") == "file"
        and not output.get("matches")
        and isinstance(output.get("path"), str)
        and isinstance(output.get("name"), str)
    ):
        return _PendingFilenameDisambiguation(
            directory=output["path"],
            requested_name=output["name"],
            source_capability="filesystem.find",
        )
    if (
        capability == "filesystem.read_text"
        and result.get("success") is False
        and isinstance(result.get("error"), dict)
        and result["error"].get("code") == CapabilityErrorCode.NOT_FOUND.value
    ):
        arguments = _result_call_arguments(transcript, message)
        path = arguments.get("path") if isinstance(arguments, dict) else None
        parsed = _extensionless_read_target(path) if isinstance(path, str) else None
        if parsed is not None:
            directory, requested_name = parsed
            return _PendingFilenameDisambiguation(
                directory=directory,
                requested_name=requested_name,
                source_capability="filesystem.read_text",
            )
    return None


def _extensionless_read_target(path: str) -> tuple[str, str] | None:
    target = Path(path)
    requested_name = target.name
    if not requested_name or requested_name in {".", ".."} or target.suffix:
        return None
    directory = str(target.parent)
    return None if not directory or directory == "." else (directory, requested_name)


def _result_call_arguments(
    transcript: list[dict[str, Any]],
    result_message: dict[str, Any],
) -> dict[str, Any] | None:
    provider_call_id = result_message.get("provider_call_id")
    capability = result_message.get("capability")
    if not isinstance(provider_call_id, str) or not isinstance(capability, str):
        return None
    for message in reversed(transcript):
        calls = message.get("capability_calls") if message.get("role") == "assistant" else None
        if not isinstance(calls, list):
            continue
        for call in calls:
            if (
                isinstance(call, dict)
                and call.get("provider_call_id") == provider_call_id
                and call.get("capability") == capability
                and isinstance(call.get("arguments"), dict)
            ):
                return call["arguments"]
    return None


def _has_following_result(
    transcript: list[dict[str, Any]],
    capability: str,
    directory: str,
) -> bool:
    pending_index = None
    for index, message in enumerate(transcript):
        pending = _pending_from_result(transcript, message)
        if pending is not None and _same_path(pending.directory, directory):
            pending_index = index
    if pending_index is None:
        return False
    return any(
        _result_matches_directory(transcript, message, capability, directory)
        for message in transcript[pending_index + 1:]
    )


def _result_matches_directory(
    transcript: list[dict[str, Any]],
    message: dict[str, Any],
    capability: str,
    directory: str,
) -> bool:
    if message.get("role") != "capability" or message.get("capability") != capability:
        return False
    output = (message.get("result") or {}).get("output") or {}
    output_path = output.get("path") or output.get("destination_path")
    if _path_matches_directory(output_path, capability, directory):
        return True
    arguments = _result_call_arguments(transcript, message)
    argument_path = arguments.get("path") if isinstance(arguments, dict) else None
    return _path_matches_directory(argument_path, capability, directory)


def _path_matches_directory(path: Any, capability: str, directory: str) -> bool:
    if not isinstance(path, str):
        return False
    if capability == "filesystem.read_text":
        return _same_path(str(Path(path).parent), directory)
    return _same_path(path, directory)


def _matching_files(requested_name: str, entries: list[dict[str, Any]]) -> list[str]:
    requested_keys = _filename_keys(requested_name)
    return [
        name
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("type") == "file"
        and isinstance((name := entry.get("name")), str)
        and bool(requested_keys & _filename_keys(name))
    ]


def _filename_keys(name: str) -> set[str]:
    value = str(name).strip().casefold()
    stem = Path(value).stem
    return {
        value,
        stem,
        _loose_filename(value),
        _loose_filename(stem),
    } - {""}


def _loose_filename(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _same_path(left: Any, right: Any) -> bool:
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and str(Path(left)).casefold() == str(Path(right)).casefold()
    )
