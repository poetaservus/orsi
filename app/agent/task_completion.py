"""Turn-local task framing and bounded semantic review, never execution authority."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.goals import TaskGoal
from app.agent.verification_scope import VERIFICATION_SCOPE_GUIDANCE


REVIEW_PREFIX = "Review the proposed final answer against the current request."


class CompletionReview(BaseModel):
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


def completion_review_message(goal: TaskGoal, pending_recovery: str | None) -> dict:
    return {"role": "system", "content": (
        REVIEW_PREFIX + " Compare every requested change and standing requirement with this turn's settled work. "
        "An unrelated answer, diagnosis, plan or read does not complete requested edits. Earlier work cannot prove "
        "this request done; source cannot prove runtime/GUI checks. "
        + VERIFICATION_SCOPE_GUIDANCE + " Account for "
        "failed, stale, denied, unavailable and unrun checks; never call them passed. Return one JSON object with goal_id="
        + json.dumps(goal.goal_id)
        + ', status="ready", "continue" or "blocked", and remaining=[strings]. '
        "Ready requires all work accounted for and remaining=[]. Continue for routine reads/corrected patches or "
        "other doable work, without another user request. Blocked requires a concrete missing input/capability, "
        "denied approval or unknown outcome; list remaining work and why. This is an assessment-only step: "
        "do not call tools, repeat checks, or gather more evidence here. If evidence or an action is missing, "
        "return continue with concrete remaining work; the normal work loop will perform it in this same turn. "
        "Existing permissions still apply; this grants no authority. In text fallback, encode this JSON in "
        "the response string of a tool=null decision."
        + (" Pending edit recovery: " + pending_recovery if pending_recovery else "")
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
