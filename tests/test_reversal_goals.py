"""Check pre-execution reversal bounds and receipt-backed durable task goals."""
from hashlib import sha256
import json
import os

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunStatus
from app.agent.goals import TaskGoal, evidence_report
from app.conversation.store import ConversationStore, TurnHistoryError
from app.inference.protocol import ModelResponse
from tests.test_bounded_edit_recovery import make_service, read, edit, call, stopped_report


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows host-write adapter")


def explained(response, text="The fresh source shows an unmet requirement; restore the original value before the remaining fix."):
    return response.model_copy(update={"assistant_text": text})


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_first_reversal_is_blocked_before_approval_and_can_finish(tmp_path, make_service, mode, bom):
    path = tmp_path / "main.py"
    path.write_bytes(bom + b"old\r\nkeep\r\n")
    service, model, approvals = make_service([read(1, path, encoding="utf-8-sig"),
        edit(2, path, "old", "new"), read(3, path, encoding="utf-8-sig"),
        edit(4, path, "new", "old"), ModelResponse.text("Saved the requested change. Tests unrun.")], mode)
    answer = service.run("Change the value in main.py and keep the other line.")
    outcome = service._turn_result
    assert len(approvals) == 1 and path.read_bytes() == bom + b"new\r\nkeep\r\n"
    assert outcome.status == AgentRunStatus.COMPLETED and outcome.semantic_corrections == 1
    rejected = outcome.settled_calls[-1]
    assert not rejected.result.success and rejected.result.metadata["edit_recovery"] == "revision_reversal"
    assert "No reversal was executed" in rejected.result.error.message
    assert answer == "Saved the requested change. Tests unrun."
    goal = outcome.goal
    assert goal.state == "reported_unverified" and goal.behaviour_verified is False
    item = goal.artifacts[0]
    assert item.saved_sha256 == sha256(path.read_bytes()).hexdigest()
    assert item.source_check_call_id == outcome.settled_calls[2].result.call_id
    assert service.store.turns()[-1].goal == goal
    restored = ConversationStore(service.store.path)
    assert restored.turns()[-1].goal == goal
    assert restored.turns()[-1].outcome.goal == goal and len(model.requests) == 5


def test_one_fresh_read_explained_rollback_is_still_approved(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, approvals = make_service([read(1, path), edit(2, path, "old", "new"),
        edit(3, path, "new", "old"), read(4, path), explained(edit(5, path, "new", "old")),
        edit(6, path, "old", "final"), read(7, path), ModelResponse.text("Changed main.py; tests unrun.")])
    service.run("Fix main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.COMPLETED and len(approvals) == 3
    assert path.read_bytes() == b"final" and outcome.semantic_corrections == 1
    assert outcome.goal.artifacts[0].source_check_call_id == outcome.settled_calls[-1].result.call_id


@pytest.mark.parametrize("missing", ["read", "explanation", "same_batch_read"])
def test_reassessment_requires_new_complete_read_and_explanation(tmp_path, make_service, missing):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    responses = [read(1, path), edit(2, path, "old", "new"), edit(3, path, "new", "old")]
    if missing == "read":
        responses.append(explained(edit(4, path, "new", "old")))
    elif missing == "explanation":
        responses.extend([read(4, path), edit(5, path, "new", "old")])
    else:
        responses.append(ModelResponse.calls((read(4, path).capability_calls[0], edit(5, path, "new", "old").capability_calls[0]),
            assistant_text="Restore the original value for the unmet requirement."))
    service, _, approvals = make_service(responses)
    report = stopped_report(service, "Fix main.py.")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert path.read_bytes() == b"new" and len(approvals) == 1
    assert "before another return" in report and service._turn_result.goal.state == "stopped"
    assert "Completion evidence:" in report


def test_second_reversal_stops_before_execution_even_with_an_explanation(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, approvals = make_service([read(1, path), edit(2, path, "old", "new"),
        edit(3, path, "new", "old"), read(4, path), explained(edit(5, path, "new", "old")),
        read(6, path), explained(edit(7, path, "old", "new"))])
    stopped_report(service, "Fix main.py.")
    assert path.read_bytes() == b"old" and len(approvals) == 2
    assert service._turn_result.settled_calls[-1].result.metadata["edit_recovery"] == "revision_reversal_limit"


def test_whole_file_overwrite_cannot_bypass_reversal_guard(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"initial")
    service, _, approvals = make_service([call(1, "filesystem.write_text", path=str(path), text="one"),
        call(2, "filesystem.write_text", path=str(path), text="two"),
        call(3, "filesystem.write_text", path=str(path), text="one"),
        ModelResponse.text("Retained latest changes; checks unrun.")], write_enabled=True)
    service.run("Update main.py.")
    assert path.read_bytes() == b"two" and len(approvals) == 2
    assert service._turn_result.settled_calls[-1].result.metadata["edit_recovery"] == "revision_reversal"


def test_new_user_request_can_reverse_a_previous_turn_without_old_guard_state(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, approvals = make_service([read(1, path), edit(2, path, "old", "new"),
        ModelResponse.text("Changed main.py; tests unrun."), read(3, path), edit(4, path, "new", "old"),
        read(5, path), ModelResponse.text("Restored main.py; tests unrun.")])
    service.run("Change main.py to the new value.")
    service.run("Undo the previous change in main.py.")
    turns = service.store.turns()
    assert len(approvals) == 2 and path.read_bytes() == b"old"
    assert turns[0].goal.objective != turns[1].goal.objective
    assert turns[0].goal.artifacts[0].source_check_call_id is None
    assert turns[1].goal.artifacts[0].source_check_call_id is not None
    assert service._turn_result.semantic_corrections == 0


def test_mutation_invalidates_old_source_check_and_truncated_read_cannot_verify(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\nkeep\n")
    service, _, _ = make_service([read(1, path), edit(2, path, "old", "new"), read(3, path),
        edit(4, path, "new", "final"), read(5, path, max_lines=1), ModelResponse.text("Done; tests unrun.")])
    answer = service.run("Fix main.py.")
    goal = service._turn_result.goal
    assert goal.artifacts[0].source_check_call_id is None
    assert goal.artifacts[0].saved_sha256 == sha256(path.read_bytes()).hexdigest()
    assert answer == "Done; tests unrun." and not goal.behaviour_verified


def test_interrupted_goal_restores_settled_evidence_without_replaying(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, _ = make_service([read(1, path), edit(2, path, "old", "new"), ModelResponse.text("Done.")])
    service.run("Fix main.py.")
    raw = json.loads(service.store.path.read_text(encoding="utf-8"))
    turn = raw["turns"][-1]
    turn["outcome"] = None
    turn["ended_at"] = None
    turn["goal"]["state"] = "active"
    turn["assistant_index"] = None
    service.store.path.write_text(json.dumps(raw), encoding="utf-8")
    recovered = ConversationStore(service.store.path)
    restored = recovered.turns()[-1]
    assert restored.goal.state == "stopped" and restored.outcome.goal == restored.goal
    assert len(restored.settled_calls) == 2 and path.read_bytes() == b"new"


@pytest.mark.parametrize("tamper", ["digest", "receipt", "objective", "verified", "dangling"])
def test_goal_evidence_cannot_be_fabricated_independently_of_receipts(tmp_path, make_service, tamper):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, _ = make_service([read(1, path), edit(2, path, "old", "new"), ModelResponse.text("Done.")])
    service.run("Fix main.py.")
    raw = json.loads(service.store.path.read_text(encoding="utf-8"))
    goal = raw["turns"][-1]["goal"]
    if tamper == "digest":
        goal["artifacts"][0]["saved_sha256"] = "0" * 64
    elif tamper == "receipt":
        goal["artifacts"][0]["source_check_call_id"] = "invented"
    elif tamper == "objective":
        goal["objective"] = "Another request"
    elif tamper == "verified":
        goal["behaviour_verified"] = True
    else:
        del raw["turns"][-1]["goal"]
    service.store.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(TurnHistoryError):
        ConversationStore(service.store.path)
    assert path.read_bytes() == b"new"


def test_verified_completion_is_not_a_model_settable_flag():
    with pytest.raises(ValidationError):
        TaskGoal(goal_id="turn-1", objective="Fix the UI", behaviour_verified=True)


def test_external_changed_revision_invalidates_source_evidence(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, model, _ = make_service([read(1, path), edit(2, path, "old", "new"), read(3, path),
        read(4, path), ModelResponse.text("Done.")])
    model.before_request[3] = lambda *_: path.write_bytes(b"external")
    answer = service.run("Fix main.py.")
    item = service._turn_result.goal.artifacts[0]
    assert item.saved_sha256 == sha256(b"new").hexdigest()
    assert item.integrity_uncertain and item.source_check_call_id is None
    assert answer == "Done." and "require review" in evidence_report(service._turn_result.goal)
    assert path.read_bytes() == b"external"


def test_legacy_history_without_goals_remains_loadable(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, _ = make_service([read(1, path), edit(2, path, "old", "new"), ModelResponse.text("Done.")])
    service.run("Fix main.py.")
    raw = json.loads(service.store.path.read_text(encoding="utf-8"))
    turn = raw["turns"][-1]
    del turn["goal"]
    del turn["outcome"]["goal"]
    service.store.path.write_text(json.dumps(raw), encoding="utf-8")
    restored = ConversationStore(service.store.path)
    assert restored.turns()[-1].goal is None
    assert len(restored.turns()[-1].settled_calls) == 2 and path.read_bytes() == b"new"


def test_truncated_read_is_insufficient_for_a_rollback(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\nkeep\n")
    service, _, approvals = make_service([read(1, path), edit(2, path, "old", "new"),
        edit(3, path, "new", "old"), read(4, path, max_lines=1), explained(edit(5, path, "new", "old"))])
    # The byte predictor cannot use this excerpt. The executor may still perform a grounded
    # edit, so pending reversals must remain recognizable independently of prediction.
    stopped_report(service, "Fix main.py.")
    assert path.read_bytes() == b"new\nkeep\n" and len(approvals) == 1


def test_missing_target_invalidates_previous_source_check(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, model, _ = make_service([read(1, path), edit(2, path, "old", "new"), read(3, path),
        read(4, path), ModelResponse.text("Review the missing target.")])
    model.before_request[3] = lambda *_: path.unlink()
    answer = service.run("Fix main.py.")
    item = service._turn_result.goal.artifacts[0]
    assert item.integrity_uncertain and item.source_check_call_id is None
    assert answer == "Review the missing target." and "require review" in evidence_report(service._turn_result.goal)


def test_attachment_only_goal_retains_the_literal_request_and_attachment(tmp_path):
    from app.agent.contracts import AgentRunResult
    store = ConversationStore(tmp_path / "chat.json")
    reference = store.attachment_store.import_bytes(b"A requested file", name="request.txt")
    turn_id = store.begin_turn("", attachments=(reference,))
    store.start_goal(turn_id)
    store.finish_turn(turn_id, AgentRunResult(status=AgentRunStatus.COMPLETED, assistant_text="Received.",
        steps=0, capability_calls=0, protocol_failures=0), "Received.")
    restored = ConversationStore(store.path)
    assert restored.turns()[-1].goal.objective == ""
    assert restored.visible_messages()[0].attachments == (reference,)


@pytest.mark.parametrize("first_mutation", ["edit", "write"])
def test_truncated_read_cannot_erase_the_settled_revision_for_whole_file_reversal(tmp_path, make_service, first_mutation):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\nkeep\n")
    change = edit(2, path, "old", "new") if first_mutation == "edit" else call(2,
        "filesystem.write_text", path=str(path), text="new\nkeep\n")
    service, _, approvals = make_service([read(1, path), change, read(3, path, max_bytes=1),
        call(4, "filesystem.write_text", path=str(path), text="old\nkeep\n"),
        ModelResponse.text("Kept the requested change; runtime checks unrun.")], write_enabled=True)
    service.run("Change main.py to the new value and keep the other line.")
    outcome = service._turn_result
    assert path.read_bytes() == b"new\nkeep\n" and len(approvals) == 1
    assert outcome.settled_calls[-1].result.metadata.get("edit_recovery") == "revision_reversal"
