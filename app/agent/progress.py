"""Honest progress at a work-budget stop, without another model request."""
from collections import Counter

from app.agent.contracts import AgentRunResult, AgentRunStatus


WORK_BUDGET_STATUSES = frozenset({AgentRunStatus.STEP_LIMIT,
    AgentRunStatus.MODEL_REQUEST_LIMIT, AgentRunStatus.CAPABILITY_CALL_LIMIT})
WORK_BUDGET_MESSAGE = "Task paused at its cloud work budget; completed operations are retained."
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
