"""Honest progress at a work-budget stop, without another model request."""
from collections import Counter
from pathlib import PureWindowsPath

from app.agent.contracts import AgentRunResult, AgentRunStatus


WORK_BUDGET_STATUSES = frozenset({AgentRunStatus.STEP_LIMIT,
    AgentRunStatus.MODEL_REQUEST_LIMIT, AgentRunStatus.CAPABILITY_CALL_LIMIT})
WORK_BUDGET_MESSAGE = "Task paused at its cloud work budget; completed operations are retained."
RECOVERY_STOP_STATUSES = frozenset({AgentRunStatus.REPEATED_CALL, AgentRunStatus.SEMANTIC_CORRECTION_LIMIT})
_OPERATIONS = {
    "filesystem.stat": ("metadata check", "metadata checks"),
    "filesystem.list": ("folder listing", "folder listings"),
    "filesystem.find": ("file lookup", "file lookups"),
    "filesystem.search": ("text search", "text searches"),
    "filesystem.read_text": ("file read", "file reads"),
    "filesystem.mkdir": ("folder creation", "folder creations"),
    "filesystem.write_text": ("file write", "file writes"),
    "filesystem.edit_text": ("file edit", "file edits"),
    "filesystem.copy": ("file copy", "file copies"),
    "filesystem.move": ("file move", "file moves"),
    "filesystem.trash": ("file trash operation", "file trash operations"),
    "application.launch": ("application launch", "application launches"),
    "skill.read_reference": ("skill reference read", "skill reference reads"),
}


def work_budget_progress(result: AgentRunResult) -> str:
    counts = Counter(item.call.capability for item in result.settled_calls if item.result.success)
    lines = ["Task paused before completion because its cloud work budget was reached."]
    if counts:
        lines.extend(["", "Completed operations:"])
        for name, count in sorted(counts.items()):
            labels = _OPERATIONS.get(name, (name + " operation", name + " operations"))
            lines.append(f"- {count} {labels[0] if count == 1 else labels[1]}")
    else:
        lines.extend(["", "No successful tool operations were recorded in this turn."])
    failures = sum(not item.result.success for item in result.settled_calls)
    if failures:
        lines.extend(["", f"Unsuccessful operations: {failures}."])
    lines.extend(["", "Completed file changes and tool results are retained. Ask me to continue; "
                  "the next turn can use the recorded results."])
    return "\n".join(lines)


def _target_name(path) -> str | None:
    if not isinstance(path, str):
        return None
    name = PureWindowsPath(path).name
    return "".join(c for c in name if c >= " " and c not in "`*[]").strip()[:180] or None


def recovery_stop_progress(result: AgentRunResult) -> str:
    """Report settled evidence locally, without another request or inferred success."""
    lines = ["Task stopped before completion.", "", result.message or "Repeated recovery did not converge."]
    changes = Counter()
    for item in result.settled_calls:
        if item.result.success and item.call.capability in {
                "filesystem.edit_text", "filesystem.write_text", "filesystem.copy", "filesystem.move",
                "filesystem.mkdir", "filesystem.trash"}:
            output = item.result.output or {}
            path = output.get("destination") or output.get("path") or item.call.arguments.get("path")
            name = _target_name(path) or "requested target"
            changes[name, item.call.capability] += 1
    if changes:
        lines.extend(["", "Settled file operations (task completion is unverified):"])
        for (name, capability), count in list(changes.items())[:8]:
            labels = _OPERATIONS[capability]
            lines.append(f"- {name}: {count} {labels[0] if count == 1 else labels[1]}.")
        if len(changes) > 8:
            lines.append(f"- {len(changes) - 8} additional changed targets are retained in the tool history.")
    else:
        lines.extend(["", "No successful file changes were recorded in this turn."])
    failures = [item for item in result.settled_calls if not item.result.success]
    if failures:
        latest = failures[-1]
        name = _target_name(latest.call.arguments.get("destination") or latest.call.arguments.get("path"))
        target = f" on {name}" if name else ""
        lines.extend(["", f"Last tool failure: {latest.call.capability}{target} ({latest.result.error.code.value}).",
            latest.result.error.message])
    lines.extend(["", "Remaining work: the requested task has not been verified complete. Review the stop reason "
        "and recorded results before continuing. Settled changes are retained and will not be replayed automatically."])
    return "\n".join(lines)
