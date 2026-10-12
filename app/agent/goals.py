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


class InteractionAssertionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    action: str = Field(max_length=32)
    target: str = Field(max_length=256)
    label: str = Field(default="", max_length=64)
    passed: bool


class VisualObservationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    label: str = Field(max_length=64)
    screenshot_path: str = Field(max_length=32767)
    screenshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["requires_review"] = "requires_review"


class VerificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    call_id: str = Field(min_length=1, max_length=128)
    project_path: str = Field(min_length=1, max_length=32767)
    kind: Literal["build", "test", "browser", "desktop"]
    passed: bool
    stale: bool = False
    screenshot_path: str | None = None
    command_passed: bool | None = None
    interaction_assertions: tuple[InteractionAssertionEvidence, ...] = Field(default=(), max_length=12)
    visual_observations: tuple[VisualObservationEvidence, ...] = Field(default=(), max_length=5)
    frame_timing_captured: bool = False


class TaskGoal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    goal_id: str = Field(pattern=r"^turn-[1-9][0-9]*$")
    # Attachment-only requests have empty text; their inputs remain on the turn's user message.
    objective: str = Field(max_length=1_000_000, repr=False)
    state: Literal["active", "reported_unverified", "stopped"] = "active"
    # A tool receipt verifies a save; a later complete matching read checks source.
    artifacts: tuple[ArtifactEvidence, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS)
    verification: tuple[VerificationEvidence, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS)
    behaviour_verified: Literal[False] = False
    # Legacy availability field retained for existing durable histories. New
    # scoped verification receipts, not this snapshot, describe executed checks.
    unavailable_checks: tuple[Literal["runtime_execution", "gui_validation"], ...] = (
        "runtime_execution", "gui_validation")


def observe_goal(goal: TaskGoal, settled) -> TaskGoal:
    """Project only bounded tool evidence, identically in runtime and durable storage."""
    call, result = settled.call, settled.result
    output = result.output or {}
    if call.capability == "shell.run" and (result.success or result.error is not None and
            result.error.code in {CapabilityErrorCode.OUTCOME_UNKNOWN, CapabilityErrorCode.CANCELLED, CapabilityErrorCode.TIMED_OUT,
                CapabilityErrorCode.INTERNAL_ERROR}):
        # General shell commands can change any account-accessible file, including
        # outside cwd. They cannot establish scoped build/test or source evidence.
        return goal.model_copy(update={
            "verification": tuple(item.model_copy(update={"stale": True}) for item in goal.verification),
            "artifacts": tuple(item.model_copy(update={"source_check_call_id": None, "integrity_uncertain": True}) for item in goal.artifacts)})
    if call.capability in {"project.verify", "project.inspect"}:
        project = output.get("project_path") or call.arguments.get("project_path")
        kind = call.arguments.get("kind")
        if isinstance(project, str) and kind in {"build", "test", "browser", "desktop"}:
            assertions, visuals = [], []
            for check in output.get('checks', [])[:12] if output.get('evidence_version') == 2 else []:
                if (check.get('action') in {'visible','text','in_view','model_loaded','scroll'} or
                        check.get('action') == 'checkpoint' and check.get('expectation') != 'observe'):
                    assertions.append(InteractionAssertionEvidence(action=check['action'],target=check.get('target',''),
                        label=check.get('label',''),passed=check.get('passed') is True))
            for observation in [*output.get('checkpoints', [])[:4], output] if output.get('evidence_version') == 2 else []:
                if isinstance(observation.get('screenshot_path'),str):
                    visuals.append(VisualObservationEvidence(label=observation.get('label','final'),
                        screenshot_path=observation['screenshot_path'],screenshot_sha256=observation.get('screenshot_sha256')))
            item = VerificationEvidence(call_id=result.call_id, project_path=project, kind=kind,
                passed=result.success and output.get("passed") is True,
                screenshot_path=output.get("screenshot_path") if isinstance(output.get("screenshot_path"), str) else None,
                command_passed=result.success and output.get('passed') is True if kind in {'build','test'} and output.get('evidence_version') == 2 else None,
                interaction_assertions=tuple(assertions),visual_observations=tuple(visuals),
                frame_timing_captured=output.get('evidence_version') == 2 and any(isinstance(c.get('frame_timing'),dict) for c in output.get('checks',[])[:12]))
            check = "runtime_execution" if call.capability == "project.verify" else "gui_validation"
            return goal.model_copy(update={"verification": (*goal.verification, item),
                "unavailable_checks": tuple(value for value in goal.unavailable_checks if value != check) if result.success else goal.unavailable_checks})
    if call.capability in {"filesystem.edit_text", "filesystem.write_text", "filesystem.copy", "filesystem.move", "filesystem.trash"} and (
            result.success or result.error is not None and result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN):
        paths = [output.get("path"), *(call.arguments.get(key) for key in ("path", "source_path", "destination_path"))]
        goal = goal.model_copy(update={"verification": tuple(item.model_copy(update={"stale": True})
            if any(isinstance(path, str) and _under(path, item.project_path) for path in paths) else item for item in goal.verification)})
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


def _under(path: str, directory: str) -> bool:
    try:
        return os.path.commonpath((path_key(path), path_key(directory))) == path_key(directory)
    except ValueError:
        return False


def goal_feedback(goal: TaskGoal) -> str:
    checked = sum(item.source_check_call_id is not None and not item.integrity_uncertain for item in goal.artifacts)
    uncertain = sum(item.integrity_uncertain for item in goal.artifacts)
    review = f" {uncertain} saved revision(s) require review." if uncertain else ""
    return (
        f"Goal {goal.goal_id}: {len(goal.artifacts)} saved file(s); {checked} matching complete rereads.{review} "
        "File receipts prove source only. Continue for a named unmet requirement. Honor requested check scope and skips; "
        "report failed/stale/unrun checks as unverified. Permissions and limits still apply. "
        + verification_report(goal)
    )


def evidence_report(goal: TaskGoal) -> str:
    if not goal.artifacts:
        return verification_report(goal) if goal.verification else ""
    checked = sum(item.source_check_call_id is not None and not item.integrity_uncertain for item in goal.artifacts)
    uncertain = sum(item.integrity_uncertain for item in goal.artifacts)
    report = (f"Completion evidence: {len(goal.artifacts)} text file(s) saved; "
        f"{checked}/{len(goal.artifacts)} subsequently checked against the saved revision. "
        "Requested behaviour is not independently verified. "
        + (verification_report(goal) if goal.verification else "Runtime execution and GUI validation were not run by ORSI."))
    if uncertain:
        report += f" {uncertain} file(s) require review because the saved revision is no longer confirmed."
    return report


def verification_report(goal: TaskGoal) -> str:
    if not goal.verification:
        return "No project verification or inspection receipts for this request."
    return "Verification receipts (only the recorded scopes): " + "; ".join(
        f"{item.kind} {'stale' if item.stale else 'passed' if item.passed else 'failed or interrupted'} [{item.call_id}]"
        + (f"; interaction assertions {sum(c.passed for c in item.interaction_assertions)}/{len(item.interaction_assertions)} passed"
            if item.interaction_assertions else '')
        + (f"; {len(item.visual_observations)} visual observations require review" if item.visual_observations else '')
        + ('; frame timing captured (smooth rendering unverified)' if item.frame_timing_captured else '')
        for item in goal.verification) + ". Screenshots require visual review."
