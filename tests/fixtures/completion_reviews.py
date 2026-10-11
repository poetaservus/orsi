"""Explicit ready assessments for legacy scripts that supply completed candidates."""
import json

from app.agent.task_completion import REVIEW_PREFIX
from app.inference.protocol import ModelResponse


def ready_review_for(messages):
    content = messages[-1].get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content)
    if not content.startswith(REVIEW_PREFIX):
        return None
    goal_id = json.loads(content.split("goal_id=", 1)[1].split(", status=", 1)[0])
    return ModelResponse.text(json.dumps({"goal_id": goal_id, "status": "ready", "remaining": []}))
