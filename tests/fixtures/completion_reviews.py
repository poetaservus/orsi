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
    catalog = json.loads(content.split('\nCurrent completion receipts: ', 1)[1].split('\n', 1)[0]) if '\nCurrent completion receipts: ' in content else []
    evidence = [{'call_id': item['call_id'], 'claim': item['observed'], 'visual_sha256': [],
                 'readiness_call_id': None} for item in catalog]
    return ModelResponse.text(json.dumps({"goal_id": goal_id, "status": "ready", "remaining": [], 'evidence': evidence}))
