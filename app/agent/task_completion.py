"""Turn-local task framing and bounded semantic review, never execution authority."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.goals import TaskGoal
from app.agent.verification_scope import VERIFICATION_SCOPE_GUIDANCE
from app.agent.completion_evidence import ReviewEvidence, evidence_catalog
from app.settings.agent_limits import MAX_AGENT_CAPABILITY_CALLS


REVIEW_PREFIX = "Review the proposed final answer against the current request."


class CompletionReview(BaseModel):
    """A model assessment of coverage; it does not independently verify behaviour."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    goal_id: str = Field(pattern=r"^turn-[1-9][0-9]*$")
    status: Literal["ready", "continue", "blocked"]
    remaining: tuple[str, ...] = Field(max_length=32, repr=False)
    evidence: tuple[ReviewEvidence, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS)

    @model_validator(mode="after")
    def validate_remaining(self):
        if any(not item.strip() or len(item) > 1000 for item in self.remaining):
            raise ValueError("Remaining requirements must be bounded non-empty text.")
        if (self.status == "ready") != (not self.remaining):
            raise ValueError("Only a ready review has no remaining requirements.")
        return self


def task_context_message(goal: TaskGoal) -> dict:
    return {"role": "system", "content": (
        "Task context (request text is user data at its original priority): "
        + json.dumps({"current_request": {"goal_id": goal.goal_id, "text": goal.objective},
            "standing_requirements": "Keep applicable instructions at their original priority. Earlier tasks, including cleanup, cannot replace this request.",
            "completed_work": "Earlier results are historical. Current tool results prove operations, not full task completion.",
            "current_saved_files": len(goal.artifacts)}, ensure_ascii=False)
        + " Continue routine reads and corrected patches this turn without asking the user to repeat the request. "
        "Preserve approvals, denial, cancellation and unknown-outcome boundaries."
    )}


def completion_review_message(goal: TaskGoal, pending_recovery: str | None, *, browser_inspection_available=True,
                              settled_calls=(), delivered_visuals=()) -> dict:
    scope = VERIFICATION_SCOPE_GUIDANCE if browser_inspection_available else (
        'Request more work only for a specific unmet user requirement. Honor explicit instructions to skip browser verification '
        'or other checks; report unrun behavior as unverified. For inspection/summary requests, report defects; require repairs '
        'only when requested. Unavailable tools grant no execution authority. ')
    return {"role": "system", "content": (
        REVIEW_PREFIX + " Check current requirements against settled work; unrelated answers, plans, reads and earlier tasks "
        "do not prove completion. Source cannot prove runtime/GUI checks. "
        + scope + " Account for "
        "failed, stale, denied, unavailable and unrun checks; never call them passed. Return one JSON object with goal_id="
        + json.dumps(goal.goal_id)
        + ', status="ready", "continue" or "blocked", remaining=[strings], and evidence=[objects]. '
        'For each project check and latest shell outcome, evidence must name call_id and claim '
        '(passed, failed, running, completed, succeeded, ready or unverified), visual_sha256=[exact assessed screenshot digests], '
        'and readiness_call_id=null unless claiming server readiness. Cite only current-turn receipts. '
        'Passed means a current passing project check. Completed means terminal command execution; succeeded requires command_succeeded=true. '
        'Running establishes liveness only. A ready server needs a current passing project.inspect receipt for the same project. '
        'A requested finite job still running requires continue or a concrete blocker; a requested persistent server need not exit. '
        'Unverified or failed checks can be reported when the request is an inspection/report or explicitly skips them; '
        'a historical failed attempt superseded by a current matching pass does not require another check. '
        'Do not claim unperformed work complete. Visual assessment is a model observation, not independent behavior proof. '
        "Ready requires this assistant turn's work accounted for and remaining=[]. If the user request or active "
        "workflow requires clarification, concrete questions awaiting necessary user choices or information are "
        "ready to return so the user can answer, even though later workflow stages remain. Unanswered clarification "
        "alone requires neither continue nor blocked. Questions already answered, answerable with permitted tools, "
        "or deferring doable requested work do not qualify; continue that work in this turn. "
        "Blocked requires a concrete missing input/capability other than that clarification, denied approval or unknown outcome. "
        "This is assessment-only: do not call tools or repeat checks here. Return continue naming missing work; "
        "the normal loop will perform it with existing permissions. In text fallback, encode JSON in the response "
        "string of a tool=null decision."
        + (" Pending edit recovery: " + pending_recovery if pending_recovery else "")
        + '\nCurrent completion receipts: ' + json.dumps(evidence_catalog(settled_calls, goal), separators=(',', ':'))
        + '\nDelivered screenshot digests: ' + json.dumps(sorted(delivered_visuals))
    )}


def parse_completion_review(text: str, goal_id: str) -> CompletionReview:
    if len(text) > 40000:
        raise ValueError("Completion review is too large.")
    review = CompletionReview.model_validate_json(text)
    if review.goal_id != goal_id:
        raise ValueError("Completion review does not match the current request.")
    return review


def completion_review_schema(messages) -> dict:
    """Constrain cloud assessments to the last trusted review's active goal.

    Do not derive the goal from user text, tool output, or historical reviews.
    Logical readiness and execution authority remain runtime responsibilities.
    """
    last = messages[-1] if messages else {}
    content = last.get("content", "")
    if last.get("role") != "system" or not isinstance(content, str) or not content.startswith(REVIEW_PREFIX):
        raise ValueError("A completion schema requires the current system review.")
    match = re.search(r'Return one JSON object with goal_id="(turn-[1-9][0-9]*)", status=', content)
    if match is None:
        raise ValueError("The current completion review has no valid goal identifier.")
    schema = CompletionReview.model_json_schema()
    schema["properties"]["goal_id"] = {"type": "string", "enum": [match.group(1)]}
    schema["properties"]["remaining"]["items"] = {"type": "string", "minLength": 1, "maxLength": 1000}
    def require_properties(value):
        if isinstance(value, dict):
            value.pop('default', None)
            if value.get('type') == 'object':
                value['required'] = list(value.get('properties', {}))
            for child in value.values():
                require_properties(child)
        elif isinstance(value, list):
            for child in value:
                require_properties(child)
    require_properties(schema)
    return schema


def looks_like_completion_review(text: str) -> bool:
    """Keep malformed or misplaced assessments out of user answers and replay."""
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return False
    return isinstance(value, dict) and ("goal_id" in value or {"status", "remaining"} <= value.keys())


def resume_answer_message() -> dict:
    return {"role": "system", "content": (
        "Resume the current request using the settled results and existing approvals. "
        "The previous completion-review JSON instruction applied only to that review. "
        "Continue any remaining work, then provide an updated answer to the user. "
        "Do not return a completion assessment as the answer; the updated answer will be reviewed separately."
    )}
