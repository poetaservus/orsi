"""One-level instruction-package discovery without registry or model state."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import stat
import sys
from typing import Literal

from app.runtime.cancellation import CancellationToken
from app.runtime.skills.contracts import (
    SkillDefinition, SkillDiscoveryIssue, SkillDiscoveryReport,
    SkillLoadError, SkillLoadErrorCode, SkillParseError,
)
from app.runtime.skills.loader import MAX_SKILL_SIZE, _inspect_chain, _validate_path, load_skill
from app.runtime.skills.diagnostics import record_skill_event


log = logging.getLogger(__name__)
MAX_DISCOVERY_ENTRIES = 1024


def discover_skills(
    *,
    global_root: Path | None = None,
    project_root: Path | None = None,
    max_bytes: int = MAX_SKILL_SIZE,
    max_entries: int = MAX_DISCOVERY_ENTRIES,
) -> SkillDiscoveryReport:
    """Scan approved scopes and return the sorted effective set plus rejections.

    global_root defaults to ~/.orsi/skills; an explicit override names that skill
    storage directory. project_root names the project whose .orsi/skills is read.
    No project scope is inferred from cwd. Missing scope directories are empty.
    Same-scope duplicate names are all rejected. Ambiguous project names also
    suppress matching global entries; a unique valid project definition wins.
    """
    if (any(root is not None and not isinstance(root, Path) for root in (global_root, project_root))
            or any(type(limit) is not int or not 0 < limit < sys.maxsize for limit in (max_bytes, max_entries))):
        raise SkillLoadError(SkillLoadErrorCode.INVALID_INPUT,
                             "Skill discovery requires pathlib.Path roots and positive integer limits.")
    scopes: list[tuple[Literal["global", "project"], Path]] = [
        ("global", global_root if global_root is not None else Path.home() / ".orsi" / "skills"),
    ]
    if project_root is not None:
        scopes.append(("project", project_root / ".orsi" / "skills"))

    effective: dict[str, SkillDefinition] = {}
    effective_sources: dict[str, str] = {}
    issues: list[SkillDiscoveryIssue] = []
    for scope, root in scopes:
        skills, rejected = _scan_scope(root, scope, max_bytes, max_entries)
        issues.extend(rejected)
        grouped: dict[str, list[SkillDefinition]] = {}
        for skill in skills:
            grouped.setdefault(skill.name, []).append(skill)
        for name in sorted(grouped):
            candidates = grouped[name]
            if len(candidates) > 1:
                effective.pop(name, None)
                issues.extend(SkillDiscoveryIssue(
                    scope, skill.source_path, "duplicate_name",
                    "Skill name is ambiguous within this scope; all matching entries were rejected.",
                ) for skill in candidates)
                continue
            if scope == "project" and name in effective:
                # Names are untrusted metadata: bound and escape them to one line.
                label = name if len(name) <= 128 else name[:125] + "..."
                log.info("[skill] project override: name=%s replaces=global", json.dumps(label, ensure_ascii=True))
            effective[name] = candidates[0]
            effective_sources[name] = scope
    for name in sorted(effective):
        record_skill_event("discovered", skill=effective[name], source=effective_sources[name])
    for issue in issues:
        record_skill_event("load_error", source=issue.scope, error_code=issue.code,
                           location=issue.source_path)
    return SkillDiscoveryReport(
        skills=tuple(effective[name] for name in sorted(effective)),
        issues=tuple(sorted(issues, key=lambda issue: (issue.scope, str(issue.source_path).casefold(),
                                                     str(issue.source_path), issue.code))),
    )


def _scan_scope(
    root: Path,
    scope: Literal["global", "project"],
    max_bytes: int,
    max_entries: int,
) -> tuple[list[SkillDefinition], list[SkillDiscoveryIssue]]:
    skills: list[SkillDefinition] = []
    issues: list[SkillDiscoveryIssue] = []
    try:
        if os.name != "nt":
            raise SkillLoadError(SkillLoadErrorCode.UNSUPPORTED_PLATFORM,
                                 "Safe skill discovery is supported on Windows only.", source_path=root)
        _validate_path(root, root)
        root = Path(os.path.abspath(root))
        info = _inspect_chain(root, root)
        if not stat.S_ISDIR(info.st_mode):
            raise SkillLoadError(SkillLoadErrorCode.INVALID_ROOT,
                                 "Skill discovery root must be a directory.", source_path=root)
        from app.execution.windows_filesystem import pinned_parent

        # The unused child path makes pinned_parent hold the scope directory itself.
        # Enumeration and each bounded skill read happen while that handle is held.
        with pinned_parent(root / "SKILL.md", CancellationToken()):
            entries: list[Path] = []
            with os.scandir(root) as scan:
                for entry in scan:
                    if len(entries) >= max_entries:
                        return [], [SkillDiscoveryIssue(
                            scope, root, "entry_limit",
                            "Skill directory exceeds the configured immediate-entry limit; scope was not loaded.",
                        )]
                    entries.append(Path(entry.path))
            for child in sorted(entries, key=lambda path: (path.name.casefold(), path.name)):
                try:
                    info = child.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        raise SkillLoadError(SkillLoadErrorCode.UNSAFE_PATH,
                                             "Skill discovery entries must not be symlinks or reparse points.",
                                             source_path=child)
                    if not stat.S_ISDIR(info.st_mode):
                        continue
                    skills.append(load_skill(child / "SKILL.md", root_path=child, max_bytes=max_bytes))
                except SkillLoadError as error:
                    if error.code != SkillLoadErrorCode.FILE_NOT_FOUND:
                        issues.append(SkillDiscoveryIssue(scope, error.source_path or child,
                                                          error.code.value, str(error)))
                except SkillParseError as error:
                    issues.append(SkillDiscoveryIssue(scope, error.source_path or child,
                                                      error.code.value, str(error)))
                except OSError:
                    issues.append(SkillDiscoveryIssue(scope, child, "io_error",
                                                      "Skill discovery entry could not be inspected safely."))
    except FileNotFoundError:
        return [], []
    except SkillLoadError as error:
        return [], [SkillDiscoveryIssue(scope, error.source_path or root, error.code.value, str(error))]
    except (OSError, ValueError):
        return [], [SkillDiscoveryIssue(scope, root, "io_error", "Skill directory could not be scanned safely.")]
    return skills, issues
