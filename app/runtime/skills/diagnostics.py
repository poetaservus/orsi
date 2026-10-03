"""Bounded decision/event logs; never retain prompts, responses or skill bodies."""
from hashlib import sha256
import json
import logging
from pathlib import Path

from app.runtime.skills.contracts import (
    SkillDefinition, SkillLoadErrorCode, SkillParseErrorCode,
)


log = logging.getLogger(__name__)
_EVENTS = frozenset({"discovered", "load_error", "catalog_error", "activated", "deactivated",
                     "activation_error", "router", "rejected", "injected"})
_RESULTS = frozenset({"not_selected", "explicit", "selected", "no_match", "empty_catalog",
                      "catalog_limit", "invalid_catalog", "input_limit", "context_limit",
                      "model_error", "timed_out", "stop_failed", "incomplete_response",
                      "invalid_response", "catalog_changed", "disabled", "skill_context_limit",
                      "cancelled"})
_ERRORS = frozenset({*(code.value for code in SkillLoadErrorCode),
                     *(code.value for code in SkillParseErrorCode),
                     "duplicate_name", "entry_limit", "refresh_failed", "invalid_name",
                     "missing_skill", "context_limit"})


def skill_source(skill: SkillDefinition | None, *, global_root: Path,
                 project_root: Path | None) -> str:
    """Classify anchored snapshot paths without reading or logging the filesystem."""
    if skill is None:
        return "unknown"
    if project_root is not None and skill.source_path.is_relative_to(project_root / ".orsi/skills"):
        return "project"
    return "global" if skill.source_path.is_relative_to(global_root) else "unknown"


def record_skill_event(event: str, *, skill: SkillDefinition | None = None,
                       name: str | None = None, instructions: str | None = None,
                       source: str | None = None, method: str | None = None,
                       router_result: str | None = None, injected: bool | None = None,
                       error_code: str | None = None, location: Path | None = None,
                       system_message_tokens: int | None = None) -> None:
    """Allowlist fields and labels; escape/bound the one untrusted name field.

    Hash the exact decoded instruction snapshot, not a later read of its file.
    Body-token size is a labelled character estimate, never a native measurement.
    No debug level enables content logging. Unknown labels become 'unknown';
    raw exceptions, metadata, source paths and model reasoning are never accepted.
    """
    if not log.isEnabledFor(logging.INFO):
        return
    values = {"event": event if event in _EVENTS else "unknown"}
    if skill is not None:
        name, instructions = skill.name, skill.instructions
    if isinstance(name, str) and isinstance(instructions, str):
        name = name if len(name) <= 128 else name[:125] + "..."
        body = instructions.encode("utf-8")
        values.update(name=name, body_sha256=sha256(body).hexdigest(), body_bytes=len(body),
                      token_size_estimate=(len(instructions) + 3) // 4,
                      token_measurement="character_estimate")
    if source is not None:
        values["source"] = source if source in {"global", "project", "unknown"} else "unknown"
    if method is not None:
        values["activation_method"] = method if method in {"explicit", "automatic", "none"} else "unknown"
    if router_result is not None:
        values["router_result"] = router_result if router_result in _RESULTS else "unknown"
    if injected is not None:
        values["injected"] = injected if type(injected) is bool else None
    if error_code is not None:
        values["error_code"] = error_code if error_code in _ERRORS else "unknown"
    if isinstance(location, Path):
        values["location_sha256"] = sha256(str(location).encode("utf-8")).hexdigest()
    if type(system_message_tokens) is int and system_message_tokens >= 0:
        values["system_message_tokens"] = system_message_tokens
    log.info("[skill] %s", json.dumps(values, ensure_ascii=True, sort_keys=True))
