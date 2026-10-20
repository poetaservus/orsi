"""A blocked proposal must not be confused with a settled or completed action."""
import json

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunResult, AgentRunStatus, BlockedCallAttempt, SettledCall
from app.agent.progress import recovery_stop_progress
from app.capabilities.contracts import CapabilityErrorCode, CapabilityFailure, CapabilityResult
from app.inference.protocol import ModelCapabilityCall


def stopped(**values):
    return AgentRunResult(status=AgentRunStatus.REPEATED_CALL,
        message="The agent stopped after repeating an identical capability call.",
        steps=4, capability_calls=4, protocol_failures=0, **values)


def test_stop_identifies_undispatched_read_separately_from_prior_rejected_edit():
    rejected = SettledCall(provider_message_id="message-3",
        call=ModelCapabilityCall(provider_call_id="edit-3", capability="filesystem.edit_text",
            arguments={"path": "C:/project/App.tsx", "old_text": "PRIVATE SOURCE"}),
        result=CapabilityResult(call_id="edit-3", capability="filesystem.edit_text", success=False,
            error=CapabilityFailure(code=CapabilityErrorCode.INVALID_ARGUMENTS,
                message="No edit executed; a current complete source read is required."), duration_ms=0))
    attempt = BlockedCallAttempt(capability="filesystem.read_text", fingerprint="a" * 64,
        repetition_count=3, target_kind="source_file", prerequisite_reason="source_read_required",
        evidence_receipt="inspection-2")
    outcome = stopped(settled_calls=(rejected,), blocked_attempt=attempt)
    report = recovery_stop_progress(outcome)

    assert "Blocked attempt: filesystem.read_text; repetition count 3. This call was not dispatched." in report
    assert "Latest settled tool failure (recorded before the stop): filesystem.edit_text on App.tsx" in report
    assert "Related inspection receipt: inspection-2." in report
    assert "PRIVATE SOURCE" not in report
    # Only executed/rejected settled proposals remain in the replayable ledger.
    assert len(outcome.settled_calls) == 1
    assert outcome.settled_calls[0].call.capability == "filesystem.edit_text"


def test_candidate_survives_stop_as_unverified_proposal_and_round_trips():
    outcome = stopped(proposed_answer="Implemented the Systems console family.",
        blocked_attempt=BlockedCallAttempt(capability="project.inspect", fingerprint="b" * 64,
            repetition_count=4, target_kind="project", prerequisite_reason="unchanged_recovery_state"),
        completion_review_current=False, completion_review_receipt_count=2)
    restored = AgentRunResult.model_validate_json(outcome.model_dump_json())
    report = recovery_stop_progress(restored)

    assert restored == outcome and restored.assistant_text is None
    assert restored.status == AgentRunStatus.REPEATED_CALL
    assert "Proposed answer retained from before the stop (completion is unverified):" in report
    assert outcome.proposed_answer in report
    assert "No relevant recovery prerequisite changed" in report
    assert not restored.completion_review_current


def test_older_stop_outcome_remains_loadable_without_new_diagnostics():
    data = json.loads(stopped().model_dump_json())
    for field in ("blocked_attempt", "proposed_answer", "completion_review_current", "completion_review_receipt_count"):
        data.pop(field)
    restored = AgentRunResult.model_validate_json(json.dumps(data))

    assert restored.blocked_attempt is None and restored.proposed_answer is None
    assert restored.completion_review_current is None
    assert restored.completion_review_receipt_count is None
    assert "Blocked attempt:" not in recovery_stop_progress(restored)


@pytest.mark.parametrize("private_field", [
    {"arguments": {"path": "C:/private", "content": "PRIVATE SOURCE"}},
    {"target_kind": "C:/private/source.ts"},
    {"prerequisite_reason": "PRIVATE ERROR CONTENT"},
    {"evidence_receipt": "C:/private/source.ts"},
])
def test_terminal_metadata_refuses_raw_arguments_paths_and_free_form_reasons(private_field):
    with pytest.raises(ValidationError):
        BlockedCallAttempt(capability="filesystem.edit_text", fingerprint="c" * 64,
            repetition_count=3, **private_field)


def test_long_candidate_report_is_bounded_without_losing_recorded_proposal():
    candidate = "A" * 30_000
    outcome = stopped(proposed_answer=candidate)
    report = recovery_stop_progress(outcome)

    assert len(report) < 25_000
    assert "full proposal remains in the recorded outcome" in report
    assert outcome.proposed_answer == candidate


@pytest.mark.parametrize(("reason", "expected"), [
    ("no_progress_observed", "no further qualifying Office progress was observed for this retry"),
    ("current_revision_already_saved", "current observed Office document revision already has a confirmed save"),
    ("snapshot_required", "complete current Office document snapshot is still required"),
    ("session_blocked", "Office session remains blocked"),
    ("connection_changed", "Office connection changed; current document discovery is required"),
    ("retry_allowance_exhausted", "one bounded retry after fresh Office evidence was already consumed"),
])
def test_office_stop_uses_runtime_reason_and_observed_revision_without_replay(reason, expected):
    attempt = BlockedCallAttempt(capability="office.save", fingerprint="d" * 64,
        repetition_count=3, target_kind="office_document",
        office_progress_revision=2, office_state_reason=reason, evidence_receipt="office-save-7")
    outcome = stopped(blocked_attempt=attempt, proposed_answer="The dashboard is prepared.")
    restored = AgentRunResult.model_validate_json(outcome.model_dump_json())
    report = recovery_stop_progress(restored)

    assert restored == outcome
    assert "Blocked attempt: office.save; repetition count 3. This call was not dispatched." in report
    assert expected in report
    assert "Observed Office progress revision: 2." in report
    assert "Related Office evidence receipt: office-save-7." in report
    assert "No relevant recovery prerequisite changed" not in report
    assert restored.settled_calls == () and restored.assistant_text is None
    assert "Proposed answer retained from before the stop (completion is unverified)" in report


def test_historical_office_attempt_without_progress_fields_is_loadable_and_honest():
    attempt = BlockedCallAttempt(capability="office.list_documents", fingerprint="e" * 64,
        repetition_count=3, prerequisite_reason="unchanged_recovery_state")
    data = json.loads(stopped(blocked_attempt=attempt).model_dump_json())
    data["blocked_attempt"].pop("office_state_reason")
    data["blocked_attempt"].pop("office_progress_revision")
    restored = AgentRunResult.model_validate_json(json.dumps(data))
    report = recovery_stop_progress(restored)

    assert restored.blocked_attempt.office_progress_revision is None
    assert restored.blocked_attempt.office_state_reason is None
    assert "no Office progress comparison was recorded for this stop" in report
    assert "no further qualifying Office progress" not in report
    assert "No relevant recovery prerequisite changed" not in report
    assert "Observed Office progress revision" not in report


@pytest.mark.parametrize("private_or_unbounded_field", [
    {"office_state_reason": "PRIVATE OFFICE TITLE"},
    {"office_progress_revision": -1},
    {"office_progress_revision": 257},
    {"office_progress_revision": "2"},
    {"office_document": "C:/private/dashboard.xlsx"},
    {"office_connection": "PRIVATE CONNECTION"},
])
def test_office_stop_metadata_rejects_private_content_and_unbounded_state(private_or_unbounded_field):
    with pytest.raises(ValidationError):
        BlockedCallAttempt(capability="office.save", fingerprint="f" * 64,
            repetition_count=3, **private_or_unbounded_field)
