"""Turn-local task framing and bounded semantic review, never execution authority."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agent.goals import TaskGoal
from app.agent.verification_scope import VERIFICATION_SCOPE_GUIDANCE
from app.agent.completion_evidence import ReviewEvidence, evidence_catalog
from app.settings.agent_limits import MAX_AGENT_CAPABILITY_CALLS


REVIEW_PREFIX = "Review the proposed final answer against the current request."


class CompletionAssessment(BaseModel):
    """A model assessment of coverage; it does not independently verify behaviour."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    goal_id: str = Field(pattern=r"^turn-[1-9][0-9]*$")
    status: Literal["ready", "continue", "blocked"]
    remaining: tuple[str, ...] = Field(max_length=32, repr=False)

    @model_validator(mode="after")
    def validate_remaining(self):
        if any(not item.strip() or len(item) > 1000 for item in self.remaining):
            raise ValueError("Remaining requirements must be bounded non-empty text.")
        if (self.status == "ready") != (not self.remaining):
            raise ValueError("Only a ready review has no remaining requirements.")
        return self


class CompletionReview(CompletionAssessment):
    """Durable semantic assessment plus independently reconstructed evidence."""
    evidence: tuple[ReviewEvidence, ...] = Field(default=(), max_length=MAX_AGENT_CAPABILITY_CALLS)
    evidence_origin: Literal['model', 'runtime'] = 'model'


class ReviewValidationError(ValueError):
    def __init__(self, reason, feedback):
        self.reason, self.feedback = reason, feedback
        super().__init__(feedback)


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
        + ', status="ready", "continue" or "blocked", and remaining=[strings]. '
        'Return exactly those three fields. The runtime supplies the receipt ledger below; do not copy receipt IDs, '
        'evidence arrays or screenshot hashes into your assessment. Assess whether the proposed answer truthfully '
        'accounts for the current request and recorded outcomes. A successful command proves only its recorded scope. '
        'Running establishes liveness only; server readiness needs an appropriate observation of the requested server. '
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
        + '\nInspection screenshots delivered in this turn: ' + str(len(delivered_visuals))
    )}


def parse_completion_review(text: str, goal_id: str) -> CompletionReview:
    if len(text) > 40000:
        raise ReviewValidationError('size_limit', 'Return only a bounded assessment with goal_id, status and remaining.')
    try:
        assessment = CompletionAssessment.model_validate_json(text)
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False)
        if any(error['type'] == 'json_invalid' for error in errors):
            reason, feedback = 'json_invalid', 'Return one JSON object only, without prose or code fences.'
        elif any(error['type'] == 'value_error' for error in errors):
            reason, feedback = 'remaining_invalid', 'Ready requires remaining=[]. Continue or blocked requires concrete remaining work.'
        else:
            reason, feedback = 'schema_invalid', 'Return exactly goal_id, status (ready, continue or blocked), and remaining (an array of strings). Do not return evidence.'
        raise ReviewValidationError(reason, feedback) from None
    review = CompletionReview(**assessment.model_dump())
    if review.goal_id != goal_id:
        raise ReviewValidationError('goal_mismatch', 'Use the current goal_id from this review request.')
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
    schema = CompletionAssessment.model_json_schema()
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
