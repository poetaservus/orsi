"""Turn-local reversal preflight and recovery from settled results, never new authority."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
import re

from app.agent.feedback import canonical_json, edit_recovery_feedback
from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError, CapabilityResult
from app.capabilities.filesystem_edit_text import FilesystemEditTextArguments, plan_edit
from app.capabilities.filesystem_write_text import FilesystemWriteTextArguments
from app.inference.protocol import ModelCapabilityCall


_FAILED_EDITS_PER_TARGET = 3
_REVISION_RETURNS = 2  # Fallback when complete bytes were unavailable for preflight.


def _path(value):
    return os.path.normcase(os.path.normpath(value)) if isinstance(value, str) and value else None


def _digest(value):
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _operation(call):
    args = call.arguments
    if not isinstance(args.get("old_text"), str) or not isinstance(args.get("new_text"), str):
        return None
    return hashlib.sha256(canonical_json({key: args.get(key, False) for key in
        ("old_text", "new_text", "replace_all")}).encode()).hexdigest()


@dataclass(frozen=True)
class EditRejection:
    reason: str
    message: str


@dataclass(frozen=True)
class EditObservation:
    stop_message: str | None = None
    feedback: str | None = None


@dataclass
class _Target:
    failures: int = 0
    recovery: bool = False
    rejected: ModelCapabilityCall | None = None
    error: str = ""
    # Only current-turn returned text is retained; no extra read or persistence.
    read: tuple[str, str | None, bool, int] | None = None
    digest: str | None = None
    last_mutation_digest: str | None = None
    revisions: set[str] = field(default_factory=set)
    returns: int = 0
    applied: dict[str, str] = field(default_factory=dict)
    source: bytes | None = None
    reversal_step: int | None = None
    reversal_digest: str | None = None
    reversal_operation: str | None = None
    rollback_used: bool = False


class EditProgressTracker:
    def __init__(self):
        self._targets: dict[str, _Target] = {}

    def before(self, call: ModelCapabilityCall, *, step: int, assistant_text: str | None = None) -> EditRejection | None:
        if call.capability not in {"filesystem.edit_text", "filesystem.write_text"}:
            return None
        state = self._targets.get(_path(call.arguments.get("path")))
        if state is None:
            return None
        if state.recovery and call.capability == "filesystem.edit_text":
            prior = f"Prior edit rejected: {state.error[:230]} "
            if state.read is None:
                return EditRejection("fresh_source_required", prior +
                    "Read current target source before attempting another edit.")
            text, digest, _, read_step = state.read
            if read_step >= step:
                return EditRejection("read_before_patch_required", prior +
                    "A recovery patch cannot be planned in the same batch as its source read. Receive the read result first.")
            old = call.arguments.get("old_text")
            if isinstance(old, str) and old and old not in text:
                return EditRejection("target_not_in_read", prior +
                    "The proposed target is absent from the fresh read. Obtain sufficient source within supported read limits.")
            expected = call.arguments.get("expected_sha256")
            if expected is not None and expected != digest:
                return EditRejection("read_digest_mismatch", prior +
                    "The proposed digest is not the fresh read's complete-file digest. Read sufficient current source.")
            if isinstance(old, str) and old and old == call.arguments.get("new_text") and old in text:
                return EditRejection("already_applied", "The requested edit makes no change. "
                    "The proposed text is already present in the fresh read; inspect task completion before another mutation.")
        operation = _operation(call) if call.capability == "filesystem.edit_text" else None
        if (operation and state.read is not None and state.read[1] is not None
                and state.applied.get(operation) == state.read[1]):
            return EditRejection("already_applied", "This exact change already succeeded on the freshly read file revision. "
                "Report the settled change instead of attempting it again.")
        predicted = self._predict(state, call)
        digest = hashlib.sha256(predicted).hexdigest() if predicted is not None else None
        pending_retry = operation is not None and operation == state.reversal_operation
        reference = state.digest or state.last_mutation_digest
        known_return = (digest is not None and reference is not None
            and digest != reference and digest in state.revisions)
        if pending_retry or known_return:
            if state.reversal_step is None:
                state.reversal_step, state.reversal_digest = step, digest
                state.reversal_operation = operation
                return EditRejection("revision_reversal", "This change targets an earlier file revision. "
                    "No reversal was executed. Reassess the latest user goal against settled changes. "
                    "If a rollback is necessary, receive a fresh complete source read, then explain the unmet "
                    "requirement or observed defect in assistant text with the revised call. Ordinary approval is still required. "
                    "Only one justified rollback is permitted in this turn; otherwise report remaining checks and stop.")
            if (state.rollback_used or digest != state.reversal_digest or state.read is None or state.source is None
                    or not state.read[2] or state.read[3] <= state.reversal_step or state.read[3] >= step
                    or state.read[1] != state.digest or not isinstance(assistant_text, str) or not assistant_text.strip()):
                return EditRejection("revision_reversal_limit", "The edit task stopped before another return to earlier file revisions. "
                    "The bounded reversal reassessment did not establish a fresh-read explanation, or its rollback was already used.")
        return None

    @staticmethod
    def _predict(state, call):
        """Use returned bytes only; this creates no new read or write authority."""
        try:
            if call.capability == "filesystem.write_text":
                args = FilesystemWriteTextArguments.model_validate(call.arguments)
                return args.text.encode("utf-8", errors="strict")
            if state.source is not None:
                args = FilesystemEditTextArguments.model_validate(call.arguments)
                return plan_edit(state.source, args).data
        except (ValueError, UnicodeError, CapabilityExecutionError):
            pass
        # Invalid patches still go through the existing normalized tool boundary.
        return None

    @staticmethod
    def _already_present(state):
        if state.read is None or state.rejected is None:
            return False
        text, _, complete, _ = state.read
        old, new = (state.rejected.arguments.get(key) for key in ("old_text", "new_text"))
        if not isinstance(old, str) or not isinstance(new, str) or not new or text.count(new) != 1:
            return False
        return old == new or complete and old not in text

    def observe(self, call: ModelCapabilityCall, result: CapabilityResult, *, step: int) -> EditObservation:
        if call.capability not in {"filesystem.read_text", "filesystem.edit_text", "filesystem.write_text"}:
            return EditObservation()
        output = result.output or {}
        path = _path(output.get("path") if result.success else call.arguments.get("path"))
        if path is None:
            return EditObservation()
        state = self._targets.setdefault(path, _Target())
        if call.capability == "filesystem.read_text":
            if not result.success or not isinstance(output.get("text"), str):
                return EditObservation()
            digest = _digest(output.get("sha256"))
            complete = (output.get("source_complete") is True or digest is not None and
                not output.get("truncated_by_bytes", False) and not output.get("truncated_by_lines", False))
            state.read = (output["text"], digest, complete, step)
            state.digest = digest
            state.source = None
            if complete and digest is not None:
                try:
                    raw = output["text"].encode("utf-8", errors="strict")
                    # utf-8-sig reads omit the BOM; retain it when reconstructing bytes.
                    for candidate in (raw, b"\xef\xbb\xbf" + raw):
                        if hashlib.sha256(candidate).hexdigest() == digest:
                            state.source = candidate
                            break
                except UnicodeError:
                    pass
            if digest is not None:
                state.revisions.add(digest)
            return EditObservation(feedback=edit_recovery_feedback(already_present=self._already_present(state))) \
                if state.recovery else EditObservation()
        if not result.success:
            reversal = result.metadata.get("edit_recovery")
            if reversal == "revision_reversal_limit":
                return EditObservation(stop_message=result.error.message)
            if reversal == "revision_reversal":
                return EditObservation(feedback=result.error.message)
            if call.capability != "filesystem.edit_text" or result.error.code != CapabilityErrorCode.INVALID_ARGUMENTS:
                return EditObservation()
            state.failures += 1
            if "edit_recovery" not in result.metadata:
                state.read = None
                state.error = result.error.message
                state.rejected = call
                state.recovery = any(part in state.error for part in (
                    "exact search text was not found", "source digest does not match", "requested edit makes no change"))
            # A preflight rejection touched no file. Its fresh read remains usable
            # once the model has received it; do not force a redundant read.
            if state.failures >= _FAILED_EDITS_PER_TARGET:
                return EditObservation(stop_message="The edit task stopped after three rejected edits to the same target.")
            return EditObservation(feedback=edit_recovery_feedback()) if state.recovery else EditObservation()

        digest = _digest(output.get("sha256"))
        predicted = self._predict(state, call)
        state.source = predicted if predicted is not None and hashlib.sha256(predicted).hexdigest() == digest else None
        state.read = None
        state.recovery = False
        if digest is not None:
            previous = state.digest or state.last_mutation_digest
            if digest != previous and (previous is not None or call.capability == "filesystem.edit_text"):
                if digest in state.revisions:
                    state.returns += 1
                else:
                    # A novel settled revision is evidence of change, not task completion.
                    state.failures = 0
                state.revisions.add(digest)
            state.digest = digest
            state.last_mutation_digest = digest
            state.revisions.add(digest)
            if digest == state.reversal_digest:
                state.rollback_used = True
            operation = _operation(call) if call.capability == "filesystem.edit_text" else None
            if operation:
                state.applied[operation] = digest
            if state.returns >= _REVISION_RETURNS:
                return EditObservation(stop_message="The edit task stopped after repeatedly returning to earlier file revisions.")
        return EditObservation()
