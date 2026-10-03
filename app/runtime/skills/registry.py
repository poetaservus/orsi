"""Authoritative, explicitly refreshed catalog of instruction-only skills."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys
from threading import Lock

from app.runtime.skills.contracts import (
    SkillDefinition, SkillDiscoveryReport, SkillLoadError, SkillLoadErrorCode,
)
from app.runtime.skills.discovery import MAX_DISCOVERY_ENTRIES, discover_skills
from app.runtime.skills.loader import MAX_SKILL_SIZE, _validate_path
from app.runtime.skills.diagnostics import record_skill_event


class SkillRegistry:
    """Own one catalog; only discover/reload read the approved skill scopes.

    Construction performs no scanning. Relative roots are anchored at construction
    so a later cwd change cannot redirect reload. No project is inferred from cwd.
    Returned definitions/reports are detached, including nested optional metadata.
    """

    def __init__(
        self,
        *,
        global_root: Path | None = None,
        project_root: Path | None = None,
        max_bytes: int = MAX_SKILL_SIZE,
        max_entries: int = MAX_DISCOVERY_ENTRIES,
    ):
        if (any(root is not None and not isinstance(root, Path) for root in (global_root, project_root))
                or any(type(limit) is not int or not 0 < limit < sys.maxsize for limit in (max_bytes, max_entries))):
            raise SkillLoadError(SkillLoadErrorCode.INVALID_INPUT,
                                 "Skill registry requires pathlib.Path roots and positive integer limits.")
        self._global_root = _anchor_root(global_root if global_root is not None else Path.home() / ".orsi" / "skills")
        self._project_root = _anchor_root(project_root) if project_root is not None else None
        self._max_bytes = max_bytes
        self._max_entries = max_entries
        self._lock = Lock()
        self._report = SkillDiscoveryReport()

    def discover(self) -> SkillDiscoveryReport:
        """Replace the entire catalog using the existing safe discovery policy.

        Reads and concurrent refreshes are serialized. Ordinary rejections are
        reported by discovery; an unexpected refresh failure clears stale skills
        before propagating the error to the caller.
        """
        with self._lock:
            try:
                report = discover_skills(
                    global_root=self._global_root,
                    project_root=self._project_root,
                    max_bytes=self._max_bytes,
                    max_entries=self._max_entries,
                )
                self._report = deepcopy(report)
            except Exception:
                self._report = SkillDiscoveryReport()
                record_skill_event("catalog_error", error_code="refresh_failed")
                raise
            return deepcopy(self._report)

    def get(self, name: str) -> SkillDefinition | None:
        """Return a detached definition by exact metadata name, or None if absent."""
        if not isinstance(name, str):
            raise TypeError("Skill lookup requires a string name.")
        with self._lock:
            return deepcopy(next((skill for skill in self._report.skills if skill.name == name), None))

    def list(self) -> tuple[SkillDefinition, ...]:
        """Return a detached, name-sorted snapshot without filesystem access."""
        with self._lock:
            return deepcopy(self._report.skills)

    def reload(self) -> SkillDiscoveryReport:
        """Rescan the same scopes; removed/rejected definitions are not retained."""
        return self.discover()

    @property
    def global_root(self) -> Path:
        """The anchored global storage directory; no filesystem access."""
        return self._global_root

    @property
    def project_root(self) -> Path | None:
        """The optional anchored project scope; no filesystem access."""
        return self._project_root

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def report(self) -> SkillDiscoveryReport:
        """Return the latest detached catalog and structured rejection report."""
        with self._lock:
            return deepcopy(self._report)


def _anchor_root(root: Path) -> Path:
    # Validate before normalization so '..' and Windows special paths cannot be
    # erased by abspath. This does not inspect or follow filesystem components.
    _validate_path(root, root)
    try:
        return Path(os.path.abspath(root))
    except (OSError, ValueError):
        raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                             "Skill registry root could not be normalized safely.", source_path=root) from None
