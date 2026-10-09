"""Runtime evidence for the user's current request, without inferring semantic success.

The request is one literal goal. Artifact checks are derived from settled receipts;
neither source text nor a model's completion claim can prove runtime behaviour.
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.capabilities.contracts import CapabilityErrorCode
from app.settings.agent_limits import MAX_AGENT_CAPABILITY_CALLS


def path_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


class ArtifactEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    path: str = Field(min_length=1, max_length=32767)
    saved_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutation_call_id: str = Field(min_length=1, max_length=128)
    source_check_call_id: str | None = Field(default=None, min_length=1, max_length=128)
    integrity_uncertain: bool = False


class TaskGoal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    goal_id: str = Field(pattern=r"^turn-[1-9][0-9]*$")
    # Attachment-only requests have empty text; their inputs remain on the turn's user message.
    objective: str = Field(max_length=1_000_000, repr=False)
    state: Literal["active", "reported_unverified", "stopped"] = "active"
    # A tool receipt verifies a save; a later complete matching read checks source.
    artifacts: tuple[ArtifactEvidence, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS)
    behaviour_verified: Literal[False] = False
    unavailable_checks: tuple[Literal["runtime_execution", "gui_validation"], ...] = (
        "runtime_execution", "gui_validation")


def observe_goal(goal: TaskGoal, settled) -> TaskGoal:
    """Project only bounded tool evidence, identically in runtime and durable storage."""
    call, result = settled.call, settled.result
    output = result.output or {}
    if call.capability in {"filesystem.copy", "filesystem.move", "filesystem.trash"}:
        # Placement can invalidate another artifact's receipt; copy leaves its source intact.
        names = ("path", "source_path", "destination_path") if call.capability != "filesystem.copy" else ("destination_path",)
        affected = {path_key(value) for key in names for value in (call.arguments.get(key),)
            if isinstance(value, str) and value}
        if result.success or result.error is not None and result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN:
            return goal.model_copy(update={"artifacts": tuple(item.model_copy(update={
                "source_check_call_id": None, "integrity_uncertain": True}) if path_key(item.path) in affected else item
                for item in goal.artifacts)})
    path = output.get("path") if result.success else call.arguments.get("path")
    if not isinstance(path, str) or not path:
        return goal
    artifacts = list(goal.artifacts)
    index = next((i for i, item in enumerate(artifacts) if path_key(item.path) == path_key(path)), None)
    digest = output.get("sha256")
    valid_digest = isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
    if result.success and call.capability in {"filesystem.edit_text", "filesystem.write_text"} and valid_digest:
        item = ArtifactEvidence(path=path, saved_sha256=digest, mutation_call_id=result.call_id)
        if index is None:
            artifacts.append(item)
        else:
            artifacts[index] = item  # Every mutation invalidates the previous source check.
    elif index is not None:
        item = artifacts[index]
        if result.success and call.capability == "filesystem.read_text":
            complete = (output.get("source_complete") is True and
                not output.get("truncated_by_bytes", False) and not output.get("truncated_by_lines", False))
            if valid_digest and digest != item.saved_sha256:
                artifacts[index] = item.model_copy(update={"source_check_call_id": None, "integrity_uncertain": True})
            elif complete and digest == item.saved_sha256:
                artifacts[index] = item.model_copy(update={"source_check_call_id": result.call_id, "integrity_uncertain": False})
        elif result.error is not None and (result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN
                or call.capability == "filesystem.read_text" and result.error.code == CapabilityErrorCode.NOT_FOUND):
            artifacts[index] = item.model_copy(update={"source_check_call_id": None, "integrity_uncertain": True})
    return goal.model_copy(update={"artifacts": tuple(artifacts)})


def finish_goal(goal: TaskGoal, *, completed: bool) -> TaskGoal:
    return goal.model_copy(update={"state": "reported_unverified" if completed else "stopped"})


def goal_feedback(goal: TaskGoal) -> str:
    checked = sum(item.source_check_call_id is not None and not item.integrity_uncertain for item in goal.artifacts)
    uncertain = sum(item.integrity_uncertain for item in goal.artifacts)
    review = f" {uncertain} saved revision(s) require review." if uncertain else ""
    return (
        f"Current request goal {goal.goal_id}: {len(goal.artifacts)} text file(s) have settled save receipts; "
        f"{checked} have a subsequent complete read matching the saved revision.{review} "
        "These are file evidence, not proof that every requested change is implemented. "
        "Compare the latest explicit user requirements with the settled work. Continue only for an identified "
        "unmet requirement, or finish with changed files and remaining/unrun checks. "
        "No runtime execution or GUI validation capability is available; do not edit speculatively to replace those checks."
    )


def evidence_report(goal: TaskGoal) -> str:
    if not goal.artifacts:
        return ""
    checked = sum(item.source_check_call_id is not None and not item.integrity_uncertain for item in goal.artifacts)
    uncertain = sum(item.integrity_uncertain for item in goal.artifacts)
    report = (f"Completion evidence: {len(goal.artifacts)} text file(s) saved; "
        f"{checked}/{len(goal.artifacts)} subsequently checked against the saved revision. "
        "Requested behaviour is not independently verified. Runtime execution and GUI validation were not run by ORSI.")
    if uncertain:
        report += f" {uncertain} file(s) require review because the saved revision is no longer confirmed."
    return report
