"""Essential repetition/receipt regressions, including the real owned bridge."""
from types import SimpleNamespace

import pytest

from app.agent.feedback import call_fingerprint
from app.agent.office_read_repetition import OfficeReadRepetition
from app.capabilities.contracts import CapabilityResult, CapabilityFailure, CapabilityErrorCode
from app.inference.protocol import ModelCapabilityCall, ModelResponse


def call(name="office.read", session="session", **arguments):
    return ModelCapabilityCall(provider_call_id="provider", capability=name, arguments={"session": session, **arguments})


def result(request, *, success=True, **output):
    return CapabilityResult(call_id="operation", capability=request.capability, success=success, duration_ms=0,
        output={"session": request.arguments["session"], **output} if success else None,
        error=None if success else CapabilityFailure(code=CapabilityErrorCode.INVALID_ARGUMENTS, message="Synthetic failure"))


@pytest.mark.parametrize("target", ["document", "authoring", "layout", "render:1:3", "table:1"])
@pytest.mark.parametrize("mutation", ["office.word_edit", "office.word_compose", "office.excel_edit", "office.revert"])
def test_only_same_session_initial_reads_renew_after_applied_receipt(target, mutation):
    tracker = OfficeReadRepetition()
    initial = call(target=target)
    other = call(session="other", target=target)
    cursor = call(target=target, cursor="old-cursor")
    repeated = {call_fingerprint(request): 2 for request in (initial, other, cursor)}
    for request in (initial, other, cursor):
        tracker.observe(request, result(request), repeated)
    edit = call(mutation)
    tracker.observe(edit, result(edit, operation="operation", outcome="applied", affected_items=1), repeated)
    assert call_fingerprint(initial) not in repeated
    assert repeated[call_fingerprint(other)] == repeated[call_fingerprint(cursor)] == 2


@pytest.mark.parametrize("change", ["unchanged", "failed", "save", "other_session", "wrong_operation", "zero_items", "wrong_result_session"])
def test_no_progress_cannot_renew_reads(change):
    tracker = OfficeReadRepetition()
    read = call(target="layout")
    repeated = {call_fingerprint(read): 2}
    tracker.observe(read, result(read), repeated)
    edit = call("office.save" if change == "save" else "office.word_edit", session="other" if change == "other_session" else "session")
    output = {"operation": "wrong" if change == "wrong_operation" else "operation",
        "outcome": "unchanged" if change == "unchanged" else "applied", "affected_items": 0 if change == "zero_items" else 1}
    if change == "wrong_result_session":
        output["session"] = "other"
    tracker.observe(edit, result(edit, success=change != "failed", **output), repeated)
    assert repeated[call_fingerprint(read)] == 2


def test_failed_read_does_not_earn_more_attempts_after_edit():
    tracker = OfficeReadRepetition()
    read = call(target="unsupported")
    repeated = {call_fingerprint(read): 2}
    tracker.observe(read, result(read, success=False), repeated)
    edit = call("office.word_edit")
    tracker.observe(edit, result(edit, operation="operation", outcome="applied", affected_items=1), repeated)
    assert repeated[call_fingerprint(read)] == 2


def test_identical_complete_composition_reports_unchanged(monkeypatch):
    from app.mcp.office_word import WordEdits
    from app.mcp.office_contracts import WordComposeArguments
    from app.mcp import office_word_document
    before = {"kind": "document", "fingerprint": "same"}
    document = SimpleNamespace(Content=SimpleNamespace(End=8))
    backend = SimpleNamespace(word_writable=lambda document: None, capture_word=lambda descriptor: dict(before))
    edits = WordEdits(SimpleNamespace(backend=backend, documents={"document": ("word", document)}))
    arguments = WordComposeArguments.model_validate({"session": "session", "snapshot": "snapshot",
        "blocks": [{"kind": "paragraph", "text": "Synthetic body"}]})
    binding = {"document": {"document": "document", "application": "word"}, "identity": "identity"}
    edits.guards["guard"] = ("office.word_compose", arguments.model_dump(mode="json"), "identity",
        ("word_document", document, 0, 8), before, {"packet": "synthetic", "plan": arguments.model_dump(mode="json")}, None, 1, "compose")
    monkeypatch.setattr(office_word_document, "write_document", lambda *args: None)
    monkeypatch.setattr(office_word_document, "verify_document", lambda *args: None)
    output = edits.execute("office.word_compose", arguments, binding, {"guard": "guard"}, "operation")
    assert output["outcome"] == "unchanged" and output["affected_items"] == 0
    assert not edits.recoveries and not edits.blocked


@pytest.mark.parametrize("stalled", [False, True])
def test_read_edit_verification_through_real_stdio_keeps_no_progress_stop(tmp_path, stalled):
    from app.agent.contracts import AgentRunStatus
    from tests.test_bounded_edit_recovery import RoomyScriptedModel
    from tests.test_office_mcp_word import connection
    from tests.test_office_mcp_live import execute
    from tests.test_office_mcp_capabilities import ROOT, runtime_for
    bridge = connection()
    model = RoomyScriptedModel([], auto_review=False)
    model.mode = "cloud"
    runtime = runtime_for(bridge, tmp_path, model, policy=bridge.resource_policy)
    approvals = []
    def approve(record):
        approvals.append(record)
        runtime.resolve_approval(record.approval_id, True)
    runtime.set_approval_requester(approve)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        def response(index, capability, arguments):
            return ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"provider-{index}", capability=capability, arguments=arguments),))
        for index in range(5):
            model.responses.append(response(index, "office.read", {"session": session, "target": "document"}))
        model.responses.append(ModelResponse.text("Synthetic loop completed"))
        def edit_at(index):
            def prepare(messages, definitions):
                view = [m["result"]["output"] for m in messages if m.get("role") == "capability"][-1]
                model.responses[0] = response(index, "office.word_edit", {"session": session, "snapshot": view["snapshot"],
                    "changes": [{"action": "replace_text", "target": view["items"][0]["target"], "text": f"Synthetic revision {index}"}]})
            return prepare
        model.before_request = {1: edit_at(1)} if stalled else {1: edit_at(1), 3: edit_at(3)}
        outcome = runtime.run([{"role": "user", "content": "Synthetic read/edit verification regression."}],
            session_id="test-session", turn_id="test-turn", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert outcome.status == (AgentRunStatus.REPEATED_CALL if stalled else AgentRunStatus.COMPLETED), outcome.message
        assert len(approvals) == (1 if stalled else 2) and len(outcome.settled_calls) == (4 if stalled else 5)
        assert [s.result.output["outcome"] for s in outcome.settled_calls if s.call.capability == "office.word_edit"] == ["applied"] * (1 if stalled else 2)
        assert all(s.result.success for s in outcome.settled_calls)
        if stalled:
            assert "office.read target=document; this call was not dispatched" in outcome.message
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]
