"""Bounded UTF-8 skill loading within an explicitly supplied directory."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import stat
import sys

from app.runtime.cancellation import CancellationToken
from app.runtime.skills.contracts import SkillDefinition, SkillLoadError, SkillLoadErrorCode
from app.runtime.skills.parser import parse_skill


MAX_SKILL_SIZE = 1024 * 1024


def load_skill(
    path: Path,
    *,
    root_path: Path,
    max_bytes: int = MAX_SKILL_SIZE,
) -> SkillDefinition:
    """Load one regular file; relative source paths are relative to root_path.

    The allowed root must be explicit. Paths are made absolute without following
    redirects; symlinks/reparse points anywhere in either chain are rejected.
    This loader uses the application's existing Windows snapshot/ancestor handles.
    Other platforms fail closed until a safe read backend is implemented.
    Parser rejections remain SkillParseError, with the normalized source path.
    """
    source_hint = path if isinstance(path, Path) else None
    if (not isinstance(path, Path) or not isinstance(root_path, Path)
            or type(max_bytes) is not int or not 0 < max_bytes < sys.maxsize):
        raise SkillLoadError(SkillLoadErrorCode.INVALID_INPUT,
                             "Skill loading requires pathlib.Path values and a positive byte limit.",
                             source_path=source_hint)
    if os.name != "nt":
        raise SkillLoadError(SkillLoadErrorCode.UNSUPPORTED_PLATFORM,
                             "Safe skill file loading is supported on Windows only.",
                             source_path=source_hint)
    for candidate in (root_path, path):
        _validate_path(candidate, source_hint)
    try:
        root = Path(os.path.abspath(root_path))
        source = Path(os.path.abspath(path if path.is_absolute() else root / path))
    except (OSError, ValueError):
        raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                             "Skill paths could not be normalized safely.", source_path=source_hint) from None
    if not source.is_relative_to(root):
        raise SkillLoadError(SkillLoadErrorCode.OUTSIDE_ROOT,
                             "Skill file is outside the allowed skill directory.", source_path=source)

    try:
        root_info = _inspect_chain(root, source)
    except FileNotFoundError:
        raise SkillLoadError(SkillLoadErrorCode.INVALID_ROOT,
                             "The allowed skill directory does not exist.", source_path=source) from None
    except OSError:
        raise SkillLoadError(SkillLoadErrorCode.IO_ERROR,
                             "The allowed skill directory could not be inspected safely.",
                             source_path=source) from None
    if not stat.S_ISDIR(root_info.st_mode):
        raise SkillLoadError(SkillLoadErrorCode.INVALID_ROOT,
                             "The allowed skill root must be a directory.", source_path=source)

    try:
        info = _inspect_chain(source, source)
        if not stat.S_ISREG(info.st_mode):
            raise SkillLoadError(SkillLoadErrorCode.NOT_FILE,
                                 "Skill source must be a regular file.", source_path=source)
        if info.st_size > max_bytes:
            raise SkillLoadError(SkillLoadErrorCode.TOO_LARGE,
                                 "Skill file exceeds the configured byte limit.", source_path=source)
        data = _read_snapshot(source, max_bytes)
    except SkillLoadError:
        raise
    except FileNotFoundError:
        raise SkillLoadError(SkillLoadErrorCode.FILE_NOT_FOUND,
                             "Skill file does not exist.", source_path=source) from None
    except ValueError:
        # The native snapshot helper independently rejects oversized files.
        raise SkillLoadError(SkillLoadErrorCode.TOO_LARGE,
                             "Skill file exceeds the configured byte limit.", source_path=source) from None
    except OSError:
        raise SkillLoadError(SkillLoadErrorCode.IO_ERROR,
                             "Skill file could not be read safely.", source_path=source) from None
    if len(data) > max_bytes:
        raise SkillLoadError(SkillLoadErrorCode.TOO_LARGE,
                             "Skill file exceeds the configured byte limit.", source_path=source)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise SkillLoadError(SkillLoadErrorCode.INVALID_ENCODING,
                             "Skill file must contain valid UTF-8 text.", source_path=source) from None
    return parse_skill(text, root_path=root, source_path=source)


def _validate_path(path: Path, source_path: Path | None) -> None:
    if (".." in path.parts or (path.anchor and not path.is_absolute())
            or path.drive.startswith("\\\\")):
        raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                             "Traversal, ambiguous paths and network/device paths are not allowed.",
                             source_path=source_path)
    parts = path.parts[1:] if path.anchor else path.parts
    if any(PureWindowsPath(part).is_reserved() or part.endswith((".", " "))
           or any(character in '<>:"|?*' or ord(character) < 32 for character in part)
           for part in parts):
        raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                             "Skill path contains an unsupported Windows path component.",
                             source_path=source_path)


def _inspect_chain(path: Path, source_path: Path):
    """Inspect parents before children so redirects are rejected before traversal."""
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                                 "Skill paths must not contain symlinks or reparse points.", source_path=source_path)
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                                 "Skill path contains a non-directory ancestor.", source_path=source_path)
    return info


def _read_snapshot(path: Path, max_bytes: int) -> bytes:
    from app.execution.windows_filesystem import pinned_parent, read_file_snapshot

    token = CancellationToken()
    with pinned_parent(path, token):
        data, _identity = read_file_snapshot(path, max_bytes, token)
    return data
