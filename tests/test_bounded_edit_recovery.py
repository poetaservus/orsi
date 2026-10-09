"""Native recovery, finite edits and durable stop reports without replay."""
from hashlib import sha256
import os

import pytest

from app.agent.contracts import AgentRunStatus
from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.completion import CompletionText, IncompleteResponseError
from app.inference.protocol import ModelCapabilityCall, ModelResponse, native_chat_messages
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig, AgentRuntimeLimits
from tests.fixtures.source_reads import python_source_fixture
from tests.test_agent_runtime import ScriptedModel


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows file recovery")


class RoomyScriptedModel(ScriptedModel):
    # Exercise runtime recovery independently of a real model's capacity.
    context_length = 131072
    max_response_tokens = 1024


def stopped_report(service, prompt):
    with pytest.raises(IncompleteResponseError) as caught:
        service.run(prompt)
    error = caught.value
    assert error.partial_text
    return CompletionText(error.partial_text, error.completion, error.completion_history)


def call(index, capability, **arguments):
    return ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"call-{index}",
        capability=capability, arguments=arguments),))


def read(index, path, **arguments):
    return call(index, "filesystem.read_text", path=str(path), **arguments)


def edit(index, path, old, new, **arguments):
    return call(index, "filesystem.edit_text", path=str(path), old_text=old, new_text=new, **arguments)


@pytest.fixture
def make_service(tmp_path):
    services = []
    def make(responses, mode="local", approvals_allowed=True, write_enabled=False):
        portable = tmp_path / f"portable-{len(services)}"
        portable.mkdir()
        model = RoomyScriptedModel(responses)
        model.mode = mode
        policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
        runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
            filesystem_read_text_enabled=True, filesystem_edit_text_enabled=True,
            filesystem_write_text_enabled=write_enabled, full_local_read_enabled=True),
            portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
        service = ConversationService(model, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
            portable_root=portable, allowed_read_roots=(tmp_path,), host_access_policy=policy)
        approvals = []
        def approve(record):
            approvals.append(record)
            service.resolve_approval(record.approval_id, approvals_allowed)
        service.set_approval_requester(approve)
        services.append(service)
        return service, model, approvals
    yield make
    for service in services:
        service.shutdown()


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("reason", ["missing", "stale"])
def test_rejected_edit_requires_fresh_grounded_read_before_corrected_approval(tmp_path, make_service, mode, reason):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\r\nkeep\r\n")
    rejected = edit(1, path, "absent" if reason == "missing" else "old", "new",
        **({"expected_sha256": "0" * 64} if reason == "stale" else {}))
    service, model, approvals = make_service([rejected, edit(2, path, "old", "new"), read(3, path),
        edit(4, path, "old", "new", expected_sha256=sha256(path.read_bytes()).hexdigest()),
        ModelResponse.text("Changed main.py; saved source checked. Execution tests not run.")], mode)
    answer = service.run("Fix the requested change in main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.COMPLETED and "Changed main.py" in answer
    assert path.read_bytes() == b"new\r\nkeep\r\n" and len(approvals) == 1
    assert outcome.semantic_corrections == 2
    assert not outcome.settled_calls[1].result.success
    assert outcome.settled_calls[1].result.metadata.get("edit_recovery") == "fresh_source_required"
    assert outcome.settled_calls[0].result.error.code.value == "invalid_arguments"
    for messages, definitions in zip(model.requests, model.definitions):
        native_chat_messages(messages, definitions)
    assert any("source" in message.get("content", "") and "rejected" in message.get("content", "")
        for message in model.requests[1] if message["role"] == "system")


def test_truncated_recovery_read_cannot_authorize_an_unseen_patch(tmp_path, make_service):
    path = tmp_path / "main.py"
    original = python_source_fixture()
    path.write_bytes(original)
    old, new = "return sum(values) - 1", "return sum(values)"
    service, _, approvals = make_service([edit(1, path, "missing method", new), read(2, path),
        edit(3, path, old, new), read(4, path, max_bytes=65536, max_lines=1000),
        edit(5, path, old, new), ModelResponse.text("Changed main.py; execution unrun.")])
    service.run("Fix draw_overlay in main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.COMPLETED and outcome.semantic_corrections == 2
    assert outcome.settled_calls[1].result.output["source_complete"] is False
    assert outcome.settled_calls[2].result.metadata.get("edit_recovery") == "target_not_in_read"
    assert outcome.settled_calls[3].result.output["source_complete"] is True
    assert len(approvals) == 1 and path.read_bytes() == original.replace(old.encode(), new.encode())


@pytest.mark.parametrize("already_applied", [False, True])
def test_noop_or_already_applied_change_is_checked_without_another_mutation(tmp_path, make_service, already_applied):
    path = tmp_path / "main.py"
    path.write_bytes(b"new\r\nkeep\r\n")
    service, model, approvals = make_service([edit(1, path, "old" if already_applied else "new", "new"),
        read(2, path), ModelResponse.text("main.py already contains the requested text; source inspected, tests unrun.")])
    service.run("Ensure the requested text is in main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.COMPLETED and outcome.semantic_corrections == 1
    assert not outcome.settled_calls[0].result.success and approvals == []
    assert "already present" in " ".join(m.get("content", "") for m in model.requests[-1])
    assert path.read_bytes() == b"new\r\nkeep\r\n"


@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_changed_arguments_and_intervening_reads_do_not_escape_target_failure_bound(tmp_path, make_service, mode):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\r\nkeep\r\n")
    responses = [edit(1, path, "missing-1", "new"), read(2, path),
        edit(3, path, "missing-2", "newer"), read(4, path), edit(5, path, "missing-3", "newest"),
        ModelResponse.text("Must not be consumed")]
    service, model, approvals = make_service(responses, mode)
    answer = stopped_report(service, "Fix main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.REPEATED_CALL and outcome.semantic_corrections == 3
    assert len(model.requests) == 5 and approvals == [] and len(outcome.settled_calls) == 5
    assert "exact search text was not found" in str(answer)
    assert answer.completion.incomplete and "Remaining" in answer
    assert path.read_bytes() == b"old\r\nkeep\r\n"


def test_reads_do_not_reset_existing_global_four_correction_limit(tmp_path, make_service):
    paths = [tmp_path / f"main-{index}.py" for index in range(2)]
    for path in paths:
        path.write_bytes(b"old")
    responses = []
    for index, path in enumerate(paths * 2):
        responses += [read(index * 2 + 1, path), edit(index * 2 + 2, path, f"missing-{index}", "new")]
    service, _, approvals = make_service(responses)
    answer = stopped_report(service, "Fix both files.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT and outcome.semantic_corrections == 4
    assert "invalid_arguments" in answer and approvals == []
    assert service.agent_runtime.limits.max_semantic_corrections == 4
    assert service.agent_runtime.limits.cloud_max_steps == AgentRuntimeLimits().cloud_max_steps == 128


@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_many_distinct_edits_keep_legitimate_read_after_mutation(tmp_path, make_service, mode):
    path = tmp_path / "main.py"
    path.write_bytes(b"stage=0\r\nkeep\r\n")
    responses = []
    for index in range(8):
        responses += [read(index * 2 + 1, path), edit(index * 2 + 2, path, f"stage={index}", f"stage={index + 1}")]
    responses += [read(17, path), ModelResponse.text("Changed main.py; saved text checked, tests unrun.")]
    service, _, approvals = make_service(responses, mode)
    service.run("Complete the requested stages in main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.COMPLETED and outcome.semantic_corrections == 0
    assert len(approvals) == 8 and path.read_bytes() == b"stage=8\r\nkeep\r\n"
    assert all(c.result.success for c in outcome.settled_calls)


def test_verified_revision_cycle_stops_without_an_arbitrary_all_edit_cap(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\r\nkeep\r\n")
    service, model, approvals = make_service([read(1, path), edit(2, path, "old", "new"), read(3, path),
        edit(4, path, "new", "old"), read(5, path), edit(6, path, "new", "old"),
        ModelResponse.text("Must not be consumed")])
    answer = stopped_report(service, "Fix main.py.")
    outcome = service._turn_result
    assert outcome.status == AgentRunStatus.REPEATED_CALL and outcome.semantic_corrections == 2
    assert len(approvals) == 1 and len(model.requests) == 6
    assert "earlier file revisions" in answer and "main.py" in answer
    assert path.read_bytes() == b"new\r\nkeep\r\n"


def test_repeated_completed_patch_is_recognized_on_a_fresh_verified_revision(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old\r\nkeep\r\n")
    service, _, approvals = make_service([edit(1, path, "old", "new"), read(2, path),
        edit(3, path, "old", "new", expected_sha256=sha256(b"new\r\nkeep\r\n").hexdigest()),
        ModelResponse.text("main.py was changed once; the repeated request was rejected. Tests unrun.")])
    service.run("Fix main.py.")
    outcome = service._turn_result
    assert len(approvals) == 1 and outcome.settled_calls[2].result.metadata.get("edit_recovery") == "already_applied"
    assert outcome.settled_calls[2].result.success is False
    assert path.read_bytes() == b"new\r\nkeep\r\n"


@pytest.mark.parametrize("stop", ["target", "identical", "semantic"])
def test_stop_report_keeps_settled_changes_and_restores_without_replay(tmp_path, make_service, stop):
    changed = tmp_path / "changed.py"
    changed.write_bytes(b"old")
    path = tmp_path / "main.py"
    path.write_bytes(b"keep")
    responses = [edit(1, changed, "old", "new")]
    if stop == "identical":
        responses += [read(2, path), read(3, path), read(4, path)]
    elif stop == "semantic":
        responses += [call(index + 2, "filesystem.stat", wrong=index) for index in range(4)]
    else:
        responses += [edit(2, path, "missing-1", "a"), read(3, path),
            edit(4, path, "missing-2", "b"), read(5, path), edit(6, path, "missing-3", "c")]
    service, model, approvals = make_service(responses)
    answer = stopped_report(service, "Fix the requested files.")
    first = service.store.turns()[-1]
    assert first.outcome.status in {AgentRunStatus.REPEATED_CALL, AgentRunStatus.SEMANTIC_CORRECTION_LIMIT}
    assert "changed.py" in answer and "Remaining" in answer and answer.completion.incomplete
    assert changed.read_bytes() == b"new" and len(approvals) == 1
    count = len(model.requests)
    reopened = ConversationStore(service.store.path)
    assert reopened.messages()[-1]["content"] == str(answer)
    assert len(reopened.turns()[-1].settled_calls) == len(first.settled_calls)
    assert len(model.requests) == count
    model.responses += [ModelResponse.text("The settled edit was retained; remaining work was stopped.")]
    service.run("What happened?")
    assert changed.read_bytes() == b"new" and len(approvals) == 1
    assert len(service.store.turns()) == 2


def test_cancellation_after_success_does_not_replay_the_mutation(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, model, approvals = make_service([edit(1, path, "old", "new"), read(2, path)])
    model.before_request[1] = lambda *_: service.cancel_current_task()
    assert service.run("Fix main.py.") == "The response was stopped."
    assert service.store.turns()[-1].outcome.status == AgentRunStatus.CANCELLED
    assert path.read_bytes() == b"new" and len(approvals) == 1


def test_worker_delivers_stop_details_without_generic_exception_log(tmp_path, make_service, caplog):
    from app.ui.worker import ConversationWorker
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, approvals = make_service([edit(1, path, "old", "new"),
        read(2, path), read(3, path), read(4, path)])
    worker = ConversationWorker(service, "Fix main.py and inspect the saved source.")
    failures, finished = [], []
    worker.failed.connect(failures.append)
    worker.finished.connect(finished.append)
    worker.run()
    assert len(failures) == 1 and not finished
    report = failures[0]
    assert isinstance(report, CompletionText) and report.completion.incomplete
    assert "main.py" in report and "Remaining" in report
    assert "A conversation turn failed in the UI worker" not in caplog.text
    assert path.read_bytes() == b"new" and len(approvals) == 1


def test_recovery_digest_must_match_the_fresh_complete_file_digest(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    service, _, approvals = make_service([edit(1, path, "old", "new", expected_sha256="0" * 64),
        read(2, path), edit(3, path, "old", "new", expected_sha256="1" * 64), read(4, path),
        edit(5, path, "old", "new", expected_sha256=sha256(b"old").hexdigest()),
        ModelResponse.text("Changed main.py; tests unrun.")])
    service.run("Fix main.py.")
    assert service._turn_result.settled_calls[2].result.metadata.get("edit_recovery") == "read_digest_mismatch"
    assert len(approvals) == 1 and path.read_bytes() == b"new"


@pytest.mark.parametrize("missing", [False, True])
def test_failed_or_unrelated_read_does_not_repair_the_rejected_target(tmp_path, make_service, missing):
    path, other = tmp_path / "main.py", tmp_path / "other.py"
    path.write_bytes(b"old")
    if not missing:
        other.write_bytes(b"old")
    service, _, approvals = make_service([edit(1, path, "absent", "new"), read(2, other),
        edit(3, path, "old", "new"), read(4, path), edit(5, path, "old", "new"),
        ModelResponse.text("Changed main.py; tests unrun.")])
    service.run("Fix main.py.")
    assert service._turn_result.settled_calls[2].result.metadata.get("edit_recovery") == "fresh_source_required"
    assert len(approvals) == 1 and path.read_bytes() == b"new"
    assert missing or other.read_bytes() == b"old"


def test_repeated_noop_variants_remain_failures_and_stop(tmp_path, make_service):
    path = tmp_path / "main.py"
    original = b"new\r\nkeep\r\n"
    path.write_bytes(original)
    service, _, approvals = make_service([edit(1, path, "new", "new"), read(2, path),
        edit(3, path, "new\r\nkeep", "new\r\nkeep"), read(4, path),
        edit(5, path, original.decode(), original.decode())])
    report = stopped_report(service, "Ensure the requested text is in main.py.")
    assert service._turn_result.semantic_corrections == 3 and approvals == []
    assert all(not s.result.success for s in service._turn_result.settled_calls if s.call.capability == "filesystem.edit_text")
    assert "makes no change" in report and path.read_bytes() == original


def test_target_aliases_do_not_create_independent_failure_allowances(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    alias = str(path).upper().replace("\\", "/")
    service, model, approvals = make_service([edit(1, path, "missing-1", "a"), read(2, path),
        edit(3, alias, "missing-2", "b"), read(4, alias), edit(5, path, "missing-3", "c")])
    stopped_report(service, "Fix main.py.")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL and len(model.requests) == 5
    assert approvals == [] and path.read_bytes() == b"old"


def test_writes_without_known_previous_digest_do_not_reset_failed_edit_allowance(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"keep")
    service, _, approvals = make_service([edit(1, path, "missing-1", "a"),
        call(2, "filesystem.write_text", path=str(path), text="keep"), read(3, path, max_bytes=1),
        edit(4, path, "missing-2", "b"), call(5, "filesystem.write_text", path=str(path), text="keep"),
        edit(6, path, "missing-3", "c")], write_enabled=True)
    report = stopped_report(service, "Inspect main.py while applying the requested fix.")
    assert service._turn_result.semantic_corrections == 3 and len(approvals) == 2
    assert "unverified" in report and path.read_bytes() == b"keep"


def test_recovery_patch_must_follow_the_model_receiving_its_read_result(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    premature = ModelResponse.calls((read(2, path).capability_calls[0], edit(3, path, "old", "new").capability_calls[0]))
    service, _, approvals = make_service([edit(1, path, "absent", "new"), premature,
        read(4, path), edit(5, path, "old", "new"), ModelResponse.text("Changed main.py; tests unrun.")])
    service.run("Fix main.py.")
    assert service._turn_result.settled_calls[2].result.metadata.get("edit_recovery") == "read_before_patch_required"
    assert len(approvals) == 1 and path.read_bytes() == b"new"


def test_returned_batch_read_can_ground_the_next_response_without_rereading(tmp_path, make_service):
    path = tmp_path / "main.py"
    path.write_bytes(b"old")
    premature = ModelResponse.calls((read(2, path).capability_calls[0], edit(3, path, "old", "new").capability_calls[0]))
    service, model, approvals = make_service([edit(1, path, "absent", "new"), premature,
        edit(4, path, "old", "new"), ModelResponse.text("Changed main.py; tests unrun.")])
    service.run("Fix main.py.")
    assert service._turn_result.semantic_corrections == 2
    assert sum(c.call.capability == "filesystem.read_text" for c in service._turn_result.settled_calls) == 1
    assert len(model.requests) == 4 and len(approvals) == 1 and path.read_bytes() == b"new"


def test_stop_report_identifies_the_failed_file_even_without_successful_changes(tmp_path, make_service):
    path = tmp_path / "remaining.py"
    path.write_bytes(b"keep")
    service, _, approvals = make_service([edit(1, path, "missing-1", "a"),
        edit(2, path, "missing-2", "b"), edit(3, path, "missing-3", "c")])
    report = stopped_report(service, "Fix remaining.py.")
    assert "remaining.py" in report and "exact search text was not found" in report
    assert approvals == [] and path.read_bytes() == b"keep"
