"""Presentation only: trusted phases, per-request correlation and a quiet UI.

No tool-name inference, execution decisions, timers or model requests live here.
Each submitted request owns one coordinator, used only on the GUI thread.
"""
from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from time import monotonic


class ProgressPhase(StrEnum):
    PREPARE = "prepare"
    WORK = "work"
    REVIEW = "review"
    FINALIZE = "finalize"


@dataclass(frozen=True)
class ProgressEvent:
    task_id: str
    run_id: str
    phase: ProgressPhase


class OperationKind(StrEnum):
    READ = "read"
    INSPECT = "inspect"
    EDIT = "edit"
    COMMAND = "command"
    CHECK = "check"
    OFFICE = "office"
    TOOL = "tool"


@dataclass(frozen=True)
class NarrativeItem:
    event_id: str
    text: str = ""  # Public assistant text accompanying an accepted native tool batch.
    operation: OperationKind | None = None
    success: bool = True


@dataclass(frozen=True)
class NarrativeEvent:
    task_id: str
    run_id: str
    item: NarrativeItem


def operation_summary(settled):
    """A settled operation label, containing no arguments or tool output."""
    name = settled.call.capability
    if name in {"filesystem.read_text", "skill.read_reference", "conversation.read_turn"}:
        kind = OperationKind.READ
    elif name in {"filesystem.stat", "filesystem.list", "filesystem.find", "filesystem.search"}:
        kind = OperationKind.INSPECT
    elif name in {"filesystem.write_text", "filesystem.edit_text", "filesystem.copy", "filesystem.move",
                  "filesystem.mkdir", "filesystem.trash"}:
        kind = OperationKind.EDIT
    elif name == "shell.run":
        kind = OperationKind.COMMAND
    elif name in {"project.verify", "project.inspect"}:
        kind = OperationKind.CHECK
    elif name.startswith("office."):
        kind = OperationKind.OFFICE
    else:
        kind = OperationKind.TOOL
    return NarrativeItem(settled.result.call_id, operation=kind, success=settled.result.success)


class SemanticProgress:
    def __init__(self, task_id, run_id, *, min_interval=12.0):
        self.task_id, self.run_id = task_id, run_id
        self.min_interval = min_interval
        self.phase = ProgressPhase.PREPARE
        self._last_phase = None
        self._last_at = None
        self.closed = False
        self.waiting = False

    def advance(self, event, *, now=None):
        if (self.closed or (event.task_id, event.run_id) != (self.task_id, self.run_id)
                or not isinstance(event.phase, ProgressPhase)):
            return None
        self.phase = event.phase
        return self.flush(now=now)

    @property
    def pending(self):
        return not self.closed and not self.waiting and self.phase != self._last_phase

    def delay_ms(self):
        elapsed = monotonic() - self._last_at if self._last_at is not None else self.min_interval
        return max(1, ceil((self.min_interval - elapsed) * 1000))

    def flush(self, *, now=None):
        """Release only the latest already-observed phase after coalescing."""
        current = monotonic() if now is None else now
        if not self.pending:
            return None
        if self._last_at is not None and current - self._last_at < self.min_interval:
            return None  # Intermediate progress may be dropped; never delays attention.
        self._last_at, self._last_phase = current, self.phase
        return self.phase

    def finish(self):
        """Return whether this is the first terminal handoff for this request."""
        if self.closed:
            return False
        self.closed = True
        return True


def attention_event(response, *, error=False, status=None, cancelled=False):
    """Use the retained run outcome, never prose or a successful tool receipt."""
    completion = getattr(response, "completion", None)
    if cancelled or status == "cancelled" or getattr(completion, "finish_reason", None) == "cancelled":
        return None
    if error or (status is not None and status != "completed") or getattr(completion, "incomplete", False):
        return "error"
    if getattr(response, "question_batch", None) is not None:
        return "question"
    return "image" if getattr(response, "generated_images", ()) else "response"
