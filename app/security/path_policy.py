from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError


@dataclass(frozen=True)
class ResolvedPath:
    requested: Path
    resolved: Path


def resolve_read_path(
    raw_path: str,
    *,
    portable_root: Path,
    allowed_roots: tuple[Path, ...],
) -> ResolvedPath:
    candidate = resolve_candidate_path(raw_path, portable_root=portable_root)
    if not allowed_roots:
        raise CapabilityExecutionError(
            CapabilityErrorCode.PERMISSION_DENIED,
            "No read roots are enabled for this capability call.",
        )

    try:
        roots = tuple(Path(root).resolve(strict=True) for root in allowed_roots)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The path could not be resolved safely.",
        ) from exc

    if not any(is_path_within(candidate.resolved, root) for root in roots):
        raise CapabilityExecutionError(
            CapabilityErrorCode.PERMISSION_DENIED,
            "The path is outside the allowed read roots.",
        )
    return candidate


def resolve_candidate_path(raw_path: str, *, portable_root: Path) -> ResolvedPath:
    """Canonicalize a path without granting access to it or touching its target."""
    if not raw_path.strip():
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The path cannot be empty.",
        )
    if "\x00" in raw_path:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INVALID_ARGUMENTS,
            "The path contains an invalid null character.",
        )
    requested = Path(raw_path)
    if os.name == "nt" and str(requested).startswith(("\\\\", "//")):
        raise CapabilityExecutionError(
            CapabilityErrorCode.PERMISSION_DENIED,
            "Network paths are not enabled for this capability.",
        )
    if not requested.is_absolute():
        requested = Path(portable_root) / requested

    try:
        resolved = requested.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CapabilityExecutionError(
            CapabilityErrorCode.INACCESSIBLE,
            "The path could not be resolved safely.",
        ) from exc

    return ResolvedPath(requested=requested, resolved=resolved)


def is_path_within(path: Path, root: Path) -> bool:
    try:
        path_value = os.path.normcase(os.path.abspath(path))
        root_value = os.path.normcase(os.path.abspath(root))
        return os.path.commonpath((path_value, root_value)) == root_value
    except ValueError:
        return False
