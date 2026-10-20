"""Bounded Office repetition recovery; synthetic receipts and scripted runtime only."""
import json
from itertools import count
from types import SimpleNamespace

import pytest

from app.agent.contracts import AgentRunStatus, BlockedCallAttempt
from app.agent.office_progress import OfficeProgress
from app.agent.progress import recovery_stop_progress
from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityFailure, CapabilityResult
from app.inference.protocol import ModelCapabilityCall, ModelResponse


_ids = count(1)


def call(name, **arguments):
    return ModelCapabilityCall(provider_call_id=f"provider-{next(_ids)}", capability=name,
                               arguments=arguments)


def receipt(request, *, error=None, **output):
    identity = f"operation-{next(_ids)}"
    if error is not None:
        return CapabilityResult(call_id=identity, capability=request.capability, success=False,
            duration_ms=0, error=CapabilityFailure(code=error, message="Synthetic rejected operation."))
    base = {"session": request.arguments["session"]} if "session" in request.arguments else {}
    if request.capability in {"office.excel_edit", "office.save"}:
        base["operation"] = identity
    return CapabilityResult(call_id=identity, capability=request.capability, success=True,
                            duration_ms=0, output={**base, **output})


def connection():
    return SimpleNamespace(exposure=SimpleNamespace(generation=1), selected_application="excel")


def attach(tracker, session="sessionA", document="docA", *, step=0):
    request = call("office.attach", application="excel", document=document)
    tracker.observe(request, receipt(request, session=session,
        document={"document": document, "application": "excel", "title": "Synthetic workbook",
                  "dirty": False, "has_path": True, "read_only": False}), {}, step=step)


def edit(session="sessionA", snapshot="snapshotA", value=2):
    return call("office.excel_edit", session=session, snapshot=snapshot,
        changes=[{"sheet": "Sheet1", "range": "A1", "values": [[value]]}])


def read(tracker, repeated, *, step, session="sessionA", snapshot="snapshotA", cursor=None,
         next_cursor=None, target="Sheet1!A1", **arguments):
    request = call("office.read", session=session, target=target,
                   **({"cursor": cursor} if cursor is not None else {}), **arguments)
    result = receipt(request, application="excel", snapshot=snapshot, cursor=next_cursor,
                     items=[{"target": "cellA", "label": "Synthetic cell", "values": [[1]]}])
    tracker.observe(request, result, repeated, step=step)
    return request


@pytest.fixture
def progress():
    tracker, bridge = OfficeProgress(), connection()
    tracker.sync(bridge)
    attach(tracker)
    return tracker, bridge


def test_save_and_discovery_renew_after_each_confirmed_revision_not_each_call_id(progress):
    tracker, _ = progress
    discovery = call("office.documents", application="excel")
    save = call("office.save", session="sessionA")
    repeated = {}
    tracker.observe(discovery, receipt(discovery, documents=[]), repeated, step=1)
    tracker.observe(save, receipt(save, saved=True), repeated, step=2)
    for revision in (1, 2, 3):
        keys = [tracker.fingerprint(request) for request in (discovery, save)]
        repeated.update({key: 2 for key in keys})
        mutation = edit(value=revision)
        assert tracker.observe(mutation, receipt(mutation, outcome="applied", affected_items=1),
                               repeated, step=revision * 3)
        assert all(key not in repeated for key in keys)
        assert tracker.observe(save, receipt(save, saved=True), repeated, step=revision * 3 + 1)
        repeated.update({key: 2 for key in keys})
        assert not tracker.observe(save, receipt(save, saved=True), repeated, step=revision * 3 + 2)
        assert all(repeated[key] == 2 for key in keys)
        assert tracker.diagnostic(save)["office_progress_revision"] == revision
        assert tracker.diagnostic(save)["office_state_reason"] == "current_revision_already_saved"


def test_save_renews_discovery_but_never_source_read_allowance(progress):
    tracker, _ = progress
    repeated = {}
    observed = read(tracker, repeated, step=1)
    discovery = call("office.documents", application="excel")
    tracker.observe(discovery, receipt(discovery, documents=[]), repeated, step=2)
    read_key, documents_key = [tracker.fingerprint(request) for request in (observed, discovery)]
    repeated.update({read_key: 2, documents_key: 2})
    save = call("office.save", session="sessionA")
    tracker.observe(save, receipt(save, saved=True), repeated, step=3)
    assert repeated[read_key] == 2
    assert documents_key not in repeated


@pytest.mark.parametrize(("first", "second"), [
    (call("office.documents"), call("office.documents", application=None, cursor=None, limit=20)),
    (call("office.save", session="sessionA"),
     call("office.save", session="sessionA", path=None, overwrite=False)),
    (call("office.read", session="sessionA"), call("office.read", session="sessionA",
     target="selection", cursor=None, max_items=100, max_chars=4096)),
])
def test_omitted_defaults_cannot_evade_repetition(progress, first, second):
    tracker, _ = progress
    assert tracker.fingerprint(first) == tracker.fingerprint(second)


def test_same_document_reattach_alias_shares_counts_and_does_not_renew(progress):
    tracker, _ = progress
    old_save = call("office.save", session="sessionA")
    repeated = {tracker.fingerprint(old_save): 2}
    attach(tracker, "sessionB")
    new_save = call("office.save", session="sessionB")
    assert tracker.fingerprint(new_save) == tracker.fingerprint(old_save)
    assert repeated[tracker.fingerprint(new_save)] == 2
    tracker.observe(old_save, receipt(old_save, saved=True), repeated, step=1)
    assert tracker.diagnostic(new_save)["office_state_reason"] == "current_revision_already_saved"


def test_unrelated_document_cannot_renew_target_reads_or_saves(progress):
    tracker, _ = progress
    attach(tracker, "sessionB", "docB")
    repeated = {}
    observed = read(tracker, repeated, step=1)
    save = call("office.save", session="sessionA")
    tracker.observe(save, receipt(save, saved=True), repeated, step=2)
    keys = [tracker.fingerprint(request) for request in (observed, save)]
    repeated.update({key: 2 for key in keys})
    mutation = edit(session="sessionB")
    tracker.observe(mutation, receipt(mutation, outcome="applied", affected_items=1), repeated, step=3)
    assert all(repeated[key] == 2 for key in keys)


@pytest.mark.parametrize("failure", ["unchanged", "wrong_operation", "wrong_session", "zero_items",
    "missing_outcome", Code.INVALID_ARGUMENTS, Code.PERMISSION_DENIED, Code.OUTCOME_UNKNOWN,
    Code.TIMED_OUT, Code.CANCELLED, Code.INVALID_OUTPUT])
def test_unconfirmed_mutation_cannot_renew_allowance(progress, failure):
    tracker, _ = progress
    repeated = {}
    observed = read(tracker, repeated, step=1)
    key = tracker.fingerprint(observed)
    repeated[key] = 2
    mutation = edit()
    if isinstance(failure, Code):
        result = receipt(mutation, error=failure)
    else:
        output = {"outcome": "unchanged" if failure == "unchanged" else "applied",
                  "affected_items": 0 if failure in {"unchanged", "zero_items"} else 1}
        if failure == "wrong_operation":
            output["operation"] = "not-the-operation"
        elif failure == "wrong_session":
            output["session"] = "other-session"
        elif failure == "missing_outcome":
            output.pop("outcome")
        result = receipt(mutation, **output)
    assert not tracker.observe(mutation, result, repeated, step=2)
    assert repeated[key] == 2
    assert tracker.diagnostic(observed)["office_progress_revision"] == 0


def test_duplicate_receipt_cannot_manufacture_revision(progress):
    tracker, _ = progress
    mutation = edit()
    result = receipt(mutation, outcome="applied", affected_items=1)
    assert tracker.observe(mutation, result, {}, step=1)
    assert not tracker.observe(mutation, result, {}, step=2)
    assert tracker.diagnostic(mutation)["office_progress_revision"] == 1


@pytest.mark.parametrize("read_case", ["complete", "paged", "before_rejection", "same_step", "wrong_snapshot",
    "unfinished", "stale_cursor", "changed_snapshot", "wrong_target", "old_generation", "denied"])
def test_rejected_intent_gets_one_retry_only_after_matching_complete_later_read(progress, read_case):
    tracker, bridge = progress
    mutation = edit(snapshot="fresh")
    if read_case == "before_rejection":
        read(tracker, {}, step=1, snapshot="fresh")
    tracker.observe(mutation, receipt(mutation, error=Code.INVALID_ARGUMENTS), {}, step=2)
    assert not tracker.renew(mutation, step=3)
    if read_case == "denied":
        tracker.observe(mutation, receipt(mutation, error=Code.PERMISSION_DENIED), {}, step=3)
    if read_case in {"paged", "unfinished", "stale_cursor", "changed_snapshot", "wrong_target"}:
        read(tracker, {}, step=3, snapshot="fresh", next_cursor="page2")
        if read_case != "unfinished":
            read(tracker, {}, step=4, snapshot="different" if read_case == "changed_snapshot" else "fresh",
                 cursor="unrelated-page" if read_case == "stale_cursor" else "page2",
                 target="Sheet1!B1" if read_case == "wrong_target" else "Sheet1!A1")
    elif read_case != "before_rejection":
        read(tracker, {}, step=3, snapshot="different" if read_case == "wrong_snapshot" else "fresh")
    if read_case == "old_generation":
        bridge.exposure.generation += 1
        tracker.sync(bridge)
    retry_step = 3 if read_case == "same_step" else 5
    assert tracker.renew(mutation, step=retry_step) is (read_case in {"complete", "paged"})
    if read_case == "same_step":
        assert tracker.renew(mutation, step=retry_step + 1)
        assert not tracker.renew(mutation, step=retry_step + 2)
    else:
        assert not tracker.renew(mutation, step=retry_step + 1)


@pytest.mark.parametrize("bound", [True, False])
def test_connection_generation_pins_sessions_and_cannot_reuse_old_snapshot(progress, bound):
    tracker, bridge = progress
    session = "sessionA" if bound else "fallback-session"
    mutation = edit(session=session, snapshot="fresh")
    tracker.observe(mutation, receipt(mutation, error=Code.INVALID_ARGUMENTS), {}, step=1)
    read(tracker, {}, step=2, session=session, snapshot="fresh")
    bridge.exposure.generation += 1
    tracker.sync(bridge)
    assert not tracker.renew(mutation, step=3)
    assert tracker.diagnostic(mutation)["office_state_reason"] == "connection_changed"
    # A fabricated later read on the old binding does not establish current progress.
    read(tracker, {}, step=4, session=session, snapshot="fresh")
    assert not tracker.renew(mutation, step=5)


def test_terminal_tracker_diagnostic_contains_only_fixed_references(progress):
    tracker, _ = progress
    attach(tracker, "PRIVATE_SESSION", "PRIVATE_DOCUMENT")
    mutation = edit(session="PRIVATE_SESSION", value="PRIVATE CONTENT")
    result = receipt(mutation, error=Code.PERMISSION_DENIED)
    tracker.observe(mutation, result, {}, step=1)
    diagnostic = tracker.diagnostic(mutation)
    assert diagnostic == {"office_progress_revision": 0, "office_state_reason": "session_blocked",
                          "evidence_receipt": result.call_id}
    attempt = BlockedCallAttempt(capability=mutation.capability, fingerprint=tracker.fingerprint(mutation),
                                repetition_count=3, target_kind="office_document", **diagnostic)
    assert "PRIVATE" not in attempt.model_dump_json()


@pytest.mark.parametrize("later_observation", ["failed_read", "incomplete_initial_read", "applied_mutation"])
def test_later_invalidating_observation_cannot_reuse_older_complete_retry_proof(progress, later_observation):
    tracker, _ = progress
    mutation = edit(snapshot="fresh")
    tracker.observe(mutation, receipt(mutation, error=Code.INVALID_ARGUMENTS), {}, step=1)
    read(tracker, {}, step=2, snapshot="fresh")
    if later_observation == "failed_read":
        request = call("office.read", session="sessionA", target="Sheet1!A1")
        tracker.observe(request, receipt(request, error=Code.INVALID_ARGUMENTS), {}, step=3)
    elif later_observation == "incomplete_initial_read":
        read(tracker, {}, step=3, snapshot="fresh", next_cursor="later-page")
    else:
        other_mutation = edit(snapshot="fresh", value=3)
        tracker.observe(other_mutation, receipt(other_mutation, outcome="applied", affected_items=1), {}, step=3)
    assert not tracker.renew(mutation, step=4)


def test_new_confirmed_save_as_destination_renews_metadata_once(progress):
    tracker, _ = progress
    initial_save = call("office.save", session="sessionA", path="C:/synthetic/first.xlsx")
    tracker.observe(initial_save, receipt(initial_save, saved=True), {}, step=1)
    discovery = call("office.documents", application="excel")
    repeated = {}
    tracker.observe(discovery, receipt(discovery, documents=[]), repeated, step=2)
    key = tracker.fingerprint(discovery)
    repeated[key] = 2
    save_as = call("office.save", session="sessionA", path="C:/synthetic/second.xlsx")
    assert tracker.observe(save_as, receipt(save_as, saved=True), repeated, step=3)
    assert key not in repeated
    repeated[key] = 2
    assert not tracker.observe(save_as, receipt(save_as, saved=True), repeated, step=4)
    assert repeated[key] == 2
    assert tracker.diagnostic(save_as)["office_progress_revision"] == 0


@pytest.mark.parametrize("malformed_session", [["PRIVATE_SESSION"], {"private": "PRIVATE_SESSION"}, 123, True, None])
def test_malformed_non_string_session_never_crashes_or_records_progress(progress, malformed_session):
    tracker, _ = progress
    mutation = edit(session=malformed_session)
    existing_documents = dict(tracker.documents)
    repeated = {tracker.fingerprint(mutation): 2}
    assert not tracker.observe(mutation, receipt(mutation, error=Code.INVALID_ARGUMENTS), repeated, step=1)
    assert not tracker.renew(mutation, step=2)
    assert isinstance(tracker.scope(mutation), str)
    assert tracker.documents == existing_documents
    diagnostic = tracker.diagnostic(mutation)
    assert diagnostic == {"office_progress_revision": 0, "office_state_reason": "no_progress_observed"}
    assert "PRIVATE" not in json.dumps(diagnostic)


def _runtime(tmp_path, responses, *, applied=True, continuing_review=False):
    from app.capabilities.registry import CapabilityRegistration
    from app.mcp.office_contracts import ExcelEditArguments, SaveArguments
    from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
    from app.capabilities.contracts import PermissionClass
    from app.agent.task_completion import REVIEW_PREFIX
    from tests.test_agent_runtime import EchoCapability, build_runtime
    from tests.test_bounded_edit_recovery import RoomyScriptedModel

    class SavedExcel(EchoCapability):
        name = "office.save"
        arguments_model = SaveArguments

        def execute(self, arguments, context):
            self.values.append(arguments.session)
            return {"session": arguments.session, "operation": context.call_id, "saved": True}

    class EditedExcel(EchoCapability):
        name = "office.excel_edit"
        arguments_model = ExcelEditArguments

        def execute(self, arguments, context):
            self.values.append(arguments.session)
            return {"session": arguments.session, "operation": context.call_id,
                    "outcome": "applied" if applied else "unchanged", "affected_items": int(applied)}

    class Model(RoomyScriptedModel):
        def respond_with_capabilities(self, messages, capabilities):
            content = messages[-1].get("content", "")
            if continuing_review and isinstance(content, str) and content.startswith(REVIEW_PREFIX):
                goal = json.loads(content.split("goal_id=", 1)[1].split(", status=", 1)[0])
                self.requests.append(messages)
                return ModelResponse.text(json.dumps({"goal_id": goal, "status": "continue",
                    "remaining": ["Workbook verification remains incomplete."]}))
            return super().respond_with_capabilities(messages, capabilities)

    model = Model(responses)
    save, mutation = SavedExcel(), EditedExcel()
    runtime, _, _, _, _ = build_runtime(tmp_path, [], capability=save, model=model)
    runtime.registry = runtime.registry.extended((CapabilityRegistration(mutation, enabled=True, model_visible=True),))
    runtime.registry.connection = connection()
    runtime.permission_gate = PermissionGate((PermissionRule("office-test", PermissionDecision.ALLOW,
        permission=PermissionClass.READ, capability_pattern="office.*"),))
    return runtime, save, mutation


def response(*requests):
    return ModelResponse.calls(requests)


def test_runtime_unchanged_save_loop_stops_undispatched_and_retains_proposal(tmp_path):
    runtime, save, _ = _runtime(tmp_path,
        [response(call("office.save", session="sessionA")), response(call("office.save", session="sessionA")),
         ModelResponse.text("The workbook was saved; verification remains pending."),
         response(call("office.save", session="sessionA", path=None, overwrite=False))], continuing_review=True)
    try:
        outcome = runtime.run([{"role": "user", "content": "Save and verify the selected workbook."}],
            session_id="session-1", turn_id="turn-1", portable_root=tmp_path,
            allowed_read_roots=(tmp_path,), goal_request="Save and verify the selected workbook.")
        assert outcome.status == AgentRunStatus.REPEATED_CALL, outcome
        assert len(save.values) == len(outcome.settled_calls) == 2
        assert outcome.blocked_attempt.capability == "office.save"
        assert outcome.blocked_attempt.office_state_reason == "current_revision_already_saved"
        assert outcome.proposed_answer == "The workbook was saved; verification remains pending."
        report = recovery_stop_progress(outcome)
        assert "This call was not dispatched" in report
        assert "Proposed answer retained from before the stop (completion is unverified)" in report
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("applied", [True, False])
def test_runtime_sequential_batch_uses_settled_edit_before_third_identical_save(tmp_path, applied):
    runtime, save, mutation = _runtime(tmp_path,
        [response(call("office.save", session="sessionA")), response(call("office.save", session="sessionA")),
         response(edit(), call("office.save", session="sessionA")), ModelResponse.text("Synthetic workflow finished.")],
        applied=applied)
    from tests.test_agent_runtime import run
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == (AgentRunStatus.COMPLETED if applied else AgentRunStatus.REPEATED_CALL), outcome
        assert len(mutation.values) == 1
        assert len(save.values) == (3 if applied else 2)
        assert len(outcome.settled_calls) == (4 if applied else 3)
        assert [item.result.output["outcome"] for item in outcome.settled_calls
                if item.call.capability == "office.excel_edit"] == ["applied" if applied else "unchanged"]
        if not applied:
            assert outcome.blocked_attempt.capability == "office.save"
    finally:
        runtime.shutdown()


def test_runtime_fresh_snapshot_renews_exactly_one_rejected_mutation_dispatch(tmp_path, monkeypatch):
    from app.capabilities.contracts import CapabilityExecutionError
    from app.capabilities.registry import CapabilityRegistration
    from app.mcp.office_contracts import ReadArguments
    from tests.test_agent_runtime import EchoCapability, run

    class ReadExcel(EchoCapability):
        name = "office.read"
        arguments_model = ReadArguments

        def execute(self, arguments, context):
            self.values.append(arguments.session)
            return {"session": arguments.session, "application": "excel", "snapshot": "fresh",
                    "cursor": None, "items": [{"target": "cellA", "label": "Synthetic cell", "values": [[1]]}]}

    requests = [response(edit(snapshot="stale")), response(edit(snapshot="stale")),
                response(call("office.read", session="sessionA", target="Sheet1!A1")),
                response(edit(snapshot="fresh")), response(edit(snapshot="fresh"))]
    runtime, save, mutation = _runtime(tmp_path, requests)
    reader = ReadExcel()
    runtime.registry = runtime.registry.extended((CapabilityRegistration(reader, enabled=True, model_visible=True),))
    runtime.registry.connection = connection()

    def reject(arguments, context):
        mutation.values.append(arguments.session)
        raise CapabilityExecutionError(Code.INVALID_ARGUMENTS, "Synthetic rejected edit; no change executed.")

    monkeypatch.setattr(mutation, "execute", reject)
    try:
        outcome = run(runtime, tmp_path)
        assert outcome.status == AgentRunStatus.REPEATED_CALL, outcome
        assert len(mutation.values) == 3 and len(reader.values) == 1 and save.values == []
        assert len(outcome.settled_calls) == 4
        assert [item.result.success for item in outcome.settled_calls] == [False, False, True, False]
        assert [item.call.arguments["snapshot"] for item in outcome.settled_calls
                if item.call.capability == "office.excel_edit"] == ["stale", "stale", "fresh"]
        assert outcome.settled_calls[2].result.output["snapshot"] == "fresh"
        assert outcome.settled_calls[2].result.output["cursor"] is None
        assert outcome.blocked_attempt.capability == "office.excel_edit"
        assert outcome.blocked_attempt.office_state_reason == "retry_allowance_exhausted"
        assert outcome.blocked_attempt.repetition_count == 3
        assert "one bounded retry after fresh Office evidence was already consumed" in recovery_stop_progress(outcome)
    finally:
        runtime.shutdown()
