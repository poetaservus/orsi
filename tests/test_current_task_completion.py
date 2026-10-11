"""Completion coverage and same-turn prerequisites, with real local tool receipts."""
import json
import os

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunStatus
from app.agent.task_completion import CompletionReview, parse_completion_review
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelResponse
from tests.test_bounded_edit_recovery import make_service, read, edit


def review(status="ready", remaining=(), goal_id="turn-1"):
    return ModelResponse.text(json.dumps({"goal_id": goal_id, "status": status, "remaining": list(remaining)}))


native = pytest.mark.skipif(os.name != "nt", reason="Native Windows host-write adapter")


@native
@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_new_request_displaces_old_cleanup_but_retains_standing_requirements(tmp_path, make_service, mode):
    path = tmp_path / "main.py"
    path.write_text("old\nkeep\n", encoding="utf-8")
    service, model, approvals = make_service([
        ModelResponse.text("Cleanup complete."), review(),
        ModelResponse.text("Cleanup complete."), review("continue", ["Change old to new in main.py"], "turn-2"),
        read(1, path), edit(2, path, "old", "new"), ModelResponse.text("Changed main.py and retained keep."),
        review(goal_id="turn-2")], mode, auto_review=False)
    service.run("Cleanup is finished. Keep the line 'keep' in future edits.")
    assert service.run("Now change old to new in main.py.") == "Changed main.py and retained keep."
    assert path.read_text() == "new\nkeep\n" and len(approvals) == 1
    turns = ConversationStore(service.store.path).turns()
    assert turns[0].goal.objective.startswith("Cleanup")
    assert turns[1].goal.objective == "Now change old to new in main.py."
    assert turns[1].outcome.completion_review.goal_id == "turn-2"
    context = next(m["content"] for m in model.requests[2] if m.get("content", "").startswith("Task context"))
    assert '"current_request": {"goal_id": "turn-2", "text": "Now change old to new in main.py."}' in context
    assert "standing_requirements" in context and "completed_work" in context
    assert "Keep the line 'keep'" in str(model.requests[2])


@native
@pytest.mark.parametrize("candidate", ["Cleanup complete.", "The bug is an off-by-one error.", "I will read and fix main.py."])
def test_unrelated_answer_diagnosis_or_plan_continues_without_new_user_turn(tmp_path, make_service, candidate):
    path = tmp_path / "main.py"
    path.write_text("old", encoding="utf-8")
    service, _, approvals = make_service([ModelResponse.text(candidate),
        review("continue", ["The requested edit has not been performed"]), read(1, path), edit(2, path, "old", "new"),
        ModelResponse.text("Changed main.py."), review()], auto_review=False)
    assert service.run("Change old to new in main.py.") == "Changed main.py."
    assert len(service.store.turns()) == 1 and len(approvals) == 1
    assert service._turn_result.status == AgentRunStatus.COMPLETED
    assert service._turn_result.semantic_corrections == 1
    assert service._turn_result.model_requests == 6


@native
@pytest.mark.parametrize("reason", ["missing", "stale"])
@pytest.mark.parametrize("assessment", ["ready", "blocked"])
def test_fresh_read_and_corrected_patch_continue_inside_review(tmp_path, make_service, reason, assessment):
    path = tmp_path / "main.py"
    path.write_text("old", encoding="utf-8")
    rejected = edit(1, path, "absent" if reason == "missing" else "old", "new",
        **({"expected_sha256": "0" * 64} if reason == "stale" else {}))
    service, _, approvals = make_service([rejected, ModelResponse.text("Please repeat the request after reading the file."),
        review(assessment, ["A fresh read is required"] if assessment == "blocked" else ()),
        read(2, path), edit(3, path, "old", "new"), ModelResponse.text("Changed main.py."), review()], auto_review=False)
    assert service.run("Change old to new in main.py.") == "Changed main.py."
    assert len(service.store.turns()) == 1 and len(approvals) == 1 and path.read_text() == "new"
    assert service._turn_result.completion_review.status == "ready"


@native
def test_review_can_perform_prerequisite_directly(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_text("old", encoding="utf-8")
    service, _, approvals = make_service([ModelResponse.text("I will fix main.py."), read(1, path),
        edit(2, path, "old", "new"), ModelResponse.text("Changed main.py."), review()], auto_review=False)
    assert service.run("Change old to new in main.py.") == "Changed main.py."
    assert path.read_text() == "new" and len(approvals) == 1


@native
@pytest.mark.parametrize("assessment", ["ready", "continue", "blocked"])
def test_denied_approval_stays_unfinished_and_survives_reload(tmp_path, make_service, assessment):
    path = tmp_path / "main.py"
    path.write_text("old", encoding="utf-8")
    service, _, approvals = make_service([read(1, path), edit(2, path, "old", "new"),
        ModelResponse.text("The edit was denied."), review(assessment,
            ["The edit remains undone because approval was denied"] if assessment != "ready" else ())],
        approvals_allowed=False, auto_review=False)
    answer = service.run("Change old to new in main.py.")
    assert "Task unfinished" in answer and answer.completion.incomplete
    assert path.read_text() == "old" and len(approvals) == 1
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.INCOMPLETE and outcome.goal.state == "stopped"
    restored = ConversationStore(service.store.path).turns()[-1]
    assert restored.outcome.completion_review.status == "blocked" and restored.goal.state == "stopped"


@native
def test_review_format_failures_stop_unfinished_within_existing_limits(tmp_path, make_service):
    service, model, _ = make_service([ModelResponse.text("Cleanup complete."),
        review(goal_id="turn-99"), ModelResponse.text("Done")], auto_review=False)
    with pytest.raises(RuntimeError, match="completion review was invalid"):
        service.run("Fix main.py.")
    assert len(model.requests) == 3 and service._turn_result.goal.state == "stopped"
    assert service._turn_result.status == AgentRunStatus.PROTOCOL_FAILURE_LIMIT


def test_completion_assessment_is_strict_and_scoped():
    for payload in [dict(goal_id="turn-1", status="ready", remaining=["Still missing"]),
                    dict(goal_id="turn-1", status="continue", remaining=[]),
                    dict(goal_id="turn-1", status="ready", remaining=[], verified=True)]:
        with pytest.raises(ValidationError):
            CompletionReview.model_validate(payload)
    with pytest.raises(ValueError):
        parse_completion_review(review(goal_id="turn-2").assistant_text, "turn-1")


@native
def test_missing_source_is_a_real_blocker_after_failed_patch(tmp_path, make_service):
    path = tmp_path / "missing.py"
    service, _, approvals = make_service([edit(1, path, "old", "new"), read(2, path),
        ModelResponse.text("The requested file is missing."), review("blocked", ["Provide the missing source file"])],
        auto_review=False)
    answer = service.run("Change old to new in missing.py.")
    assert "Task unfinished" in answer and not approvals and not path.exists()
    assert service._turn_result.goal.state == "stopped"


@native
def test_failed_fresh_read_cannot_reuse_an_earlier_already_present_check(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_text("new", encoding="utf-8")
    service, model, approvals = make_service([edit(1, path, "old", "new"), read(2, path), read(3, path),
        ModelResponse.text("Already contains the requested text."), review()], auto_review=False)
    model.before_request[2] = lambda *_: path.unlink()
    answer = service.run("Ensure main.py contains new.")
    assert answer.completion.incomplete and service._turn_result.goal.state == "stopped"
    assert service._turn_result.completion_review.status == "blocked" and not approvals


def test_completion_review_consumes_the_existing_model_budget(tmp_path):
    from tests.test_agent_runtime import build_runtime
    from app.settings.agent import AgentRuntimeLimits
    runtime, model, _, _, _ = build_runtime(tmp_path, [ModelResponse.text("Done.")],
        limits=AgentRuntimeLimits(max_model_requests=1))
    try:
        result = runtime.run([{"role": "user", "content": "Answer the request"}], session_id="session", turn_id="turn-1",
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request="Answer the request")
        assert result.status == AgentRunStatus.MODEL_REQUEST_LIMIT and result.goal.state == "stopped"
        assert result.model_requests == len(model.requests) == 1
    finally:
        runtime.shutdown()


def test_completion_review_works_through_constrained_text_fallback(tmp_path):
    from tests.test_agent_runtime import build_runtime
    from tests.test_opencode_tool_resolution_port import TextOnlyStructuredFallbackModel
    runtime, _, _, _, _ = build_runtime(tmp_path, [])
    model = TextOnlyStructuredFallbackModel([
        json.dumps({"tool": None, "arguments": {}, "response": "The requested answer."}),
        json.dumps({"tool": None, "arguments": {}, "response": review().assistant_text})])
    runtime.model = model
    try:
        result = runtime.run([{"role": "user", "content": "Answer the request"}], session_id="session", turn_id="turn-1",
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request="Answer the request")
        assert result.status == AgentRunStatus.COMPLETED and result.assistant_text == "The requested answer."
        assert result.model_requests == 3 and len(model.requests) == 2
        assert result.completion_review.status == "ready"
    finally:
        runtime.shutdown()


def test_goal_frame_does_not_replace_user_message_when_no_system_prompt_is_supplied(tmp_path):
    from tests.test_agent_runtime import build_runtime, capability_call
    runtime, model, echo, _, _ = build_runtime(tmp_path, [capability_call(1), ModelResponse.text("Done."), review()])
    try:
        result = runtime.run([{"role": "user", "content": "Perform this current request"}],
            session_id="session", turn_id="turn-1", portable_root=tmp_path, allowed_read_roots=(tmp_path,),
            goal_request="Perform this current request")
        assert result.status == AgentRunStatus.COMPLETED and echo.values == ["hello"]
        assert all(any(m.get("role") == "user" and m.get("content") == "Perform this current request"
            for m in request) for request in model.requests)
    finally:
        runtime.shutdown()


def test_internal_review_is_not_replayed_as_the_assistant_answer(tmp_path):
    from tests.test_agent_runtime import build_runtime
    from tests.test_openai_replay import evidence, message
    answer = ModelResponse.text("The requested answer.").model_copy(update={
        "openai_response": evidence([message("The requested answer.")], identity="resp-answer")})
    assessment = review().model_copy(update={"openai_response": evidence([message(review().assistant_text)], identity="resp-review")})
    runtime, _, _, _, _ = build_runtime(tmp_path, [answer, assessment])
    retained = []
    try:
        result = runtime.run([{"role": "user", "content": "Answer the request"}], session_id="session", turn_id="turn-1",
            portable_root=tmp_path, allowed_read_roots=(tmp_path,), goal_request="Answer the request",
            response_observer=lambda identity, replay: retained.append(replay))
        assert result.assistant_text == "The requested answer."
        assert [item.response_id for item in retained] == ["resp-answer"]
        assert result.completion_review.status == "ready" and len(result.completion_history) == 2
    finally:
        runtime.shutdown()
