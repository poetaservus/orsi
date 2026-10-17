"""Essential Word workflow checks; no user documents or model requests."""
from types import SimpleNamespace
import pytest
from app.mcp.office_word_workflow import WordWorkflow
from app.mcp.office_contracts import WordReviewArguments
from app.mcp.office_excel import OfficeConflict


def review(w, defects=(), met=True):
    w.page_count = 2
    w.rendered.update((1, 2))
    w.delivered.update((1, 2))
    w.inspect(WordReviewArguments(session="s", revision=w.revision,
        findings=list(defects), requirements_checked=["Requested title and legible layout"], requirements_met=met))


DEFECT = {"location": "page 1 title", "defect": "Title is Draft", "requirement": "Title must be Final"}


def test_clean_inspection_save_finishes_without_rewrite():
    w = WordWorkflow(); w.sync("initial"); w.applied("composed")
    review(w)
    w.save("save1")
    assert w.evidence()["verified_saved"]
    with pytest.raises(OfficeConflict, match="concrete"):
        w.before_edit()


def test_current_concrete_defects_authorize_correction_and_invalidate_evidence():
    w = WordWorkflow(); w.sync("a"); w.applied("b")
    review(w, [DEFECT], False); w.save("saved-draft")
    w.authoring = {"snapshot": "fresh", "revision": "b"}
    w.before_edit(); w.applied("c")
    e = w.evidence()
    assert e["review"] is None and e["current_save"] is None
    assert e["image_pages"] == e["rendered_pages"] == []
    assert e["authoring_snapshot"] is None
    assert e["save_receipts"] == [{"revision": "b", "operation": "saved-draft"}]
    assert not e["verified_saved"]


def test_alternating_revisions_detected_without_snapshot_identity_or_edit_cap():
    w = WordWorkflow(); w.sync("a"); w.applied("b")
    review(w, [DEFECT], False); w.before_edit(); w.applied("c")
    other = {**DEFECT, "defect": "Title has wrong capitalization"}
    review(w, [other], False); w.before_edit(); w.applied("b")
    assert w.evidence()["revision_repeated"]
    with pytest.raises(OfficeConflict, match="cycle"):
        review(w, [DEFECT], False)
    # A distinct requirement may justify legitimate further corrections.
    review(w, [{**DEFECT, "requirement": "Add the newly requested subtitle"}], False)
    w.before_edit()


def test_layout_and_partial_or_stale_images_do_not_authorize_review():
    w = WordWorkflow(); w.sync("a"); w.page_count = 2; w.rendered.update((1, 2)); w.delivered.add(1)
    args = WordReviewArguments(session="s", revision="a", findings=[], requirements_checked=["Title"], requirements_met=True)
    with pytest.raises(OfficeConflict, match="every"):
        w.inspect(args)
    w.sync("b")
    with pytest.raises(OfficeConflict, match="old"):
        w.inspect(args)


def test_many_distinct_necessary_corrections_have_no_arbitrary_cap():
    w = WordWorkflow(); w.sync("initial"); w.applied("r0")
    for i in range(30):
        review(w, [{**DEFECT, "location": f"page 1 item {i}"}], False)
        w.before_edit(); w.applied(f"r{i+1}")
    review(w); w.save("final")
    assert w.evidence()["verified_saved"]

@pytest.mark.parametrize("verified,closing_failure", [(True, False), (True, True), (False, False)])
def test_runtime_word_completion_and_receipts(tmp_path, verified, closing_failure):
    from app.agent.contracts import AgentRunStatus
    from app.inference.protocol import ModelCapabilityCall, ModelResponse
    from app.security.permissions import PermissionGate, PermissionRule, PermissionDecision
    from app.capabilities.contracts import PermissionClass
    from tests.test_agent_runtime import EchoCapability, build_runtime, run
    from tests.test_bounded_edit_recovery import RoomyScriptedModel

    w = WordWorkflow(); w.sync("a"); w.applied("b")
    if verified:
        review(w)
    w.save("save-receipt")

    class SavedWord(EchoCapability):
        name = "office.save"
        def execute(self, arguments, context):
            self.values.append(arguments.value)
            return {"saved": True, "word_workflow": w.evidence()}

    call = ModelResponse.calls((ModelCapabilityCall(provider_call_id="save", capability="office.save", arguments={"value": "save"}),))
    ending = [RuntimeError("closing unavailable")] if closing_failure else [ModelResponse.text("Done")]
    if not verified:
        ending.append(ModelResponse.text("Blocked: page and requirements verification unfinished."))
    model = RoomyScriptedModel([call, *ending], auto_review=False)
    runtime, _, tool, _, _ = build_runtime(tmp_path, [], capability=SavedWord(), model=model)
    runtime.permission_gate = PermissionGate((PermissionRule("word-test", PermissionDecision.ALLOW,
        permission=PermissionClass.READ, capability_pattern="office.save"),))
    result = run(runtime, tmp_path)
    assert tool.values == ["save"]
    assert result.settled_calls[0].result.output["saved"]
    if verified and not closing_failure:
        assert result.status == AgentRunStatus.COMPLETED
        assert len(model.requests) == 2
    else:
        assert result.status != AgentRunStatus.COMPLETED
        assert "Successful save receipt for this revision: save-receipt" in result.partial_text
        if not verified:
            assert "remain unverified" in result.partial_text
    runtime.shutdown()


def test_image_transfer_requires_complete_current_bytes():
    from app.mcp.office_word_render import WordRenders
    from app.mcp.office_com import OfficeUnavailable
    w = WordWorkflow(); w.sync("current")
    renderer = WordRenders(SimpleNamespace(word=SimpleNamespace(workflow=lambda binding: w)))
    renderer.images["snapshot"] = ("s", "identity", {1: b"x" * 24001})
    renderer.revisions["snapshot"] = "current"
    binding = {"identity": "identity"}
    data = {"session": "s", "snapshot": "snapshot", "page": 1, "offset": 24000}
    renderer.chunk(data, binding)
    assert not w.delivered
    renderer.chunk({**data, "offset": 0}, binding)
    renderer.chunk(data, binding)
    assert w.delivered == {1}
    w.sync("changed")
    with pytest.raises(OfficeUnavailable, match="old revision"):
        renderer.chunk({**data, "offset": 0}, binding)
    assert not w.delivered


def test_review_requires_verified_images_sent_to_this_model():
    from app.agent.word_evidence import WordTurnProgress
    from app.inference.protocol import ModelCapabilityCall
    progress = WordTurnProgress()
    progress.evidence["s"] = {"revision": "current", "page_count": 2}
    call = ModelCapabilityCall(provider_call_id="review", capability="office.word_review",
                               arguments={"session": "s", "revision": "current"})
    assert progress.before(call).reason == "word_inspection"
    result = SimpleNamespace(output={"word_workflow": {"revision": "current"},
        "items": [{"text": '{"page":1}'}, {"text": '{"page":2}'}]})
    progress.images_delivered(call, result, {"role": "system", "content": "Pixels unavailable"})
    assert progress.before(call) is not None
    progress.images_delivered(call, result, {"content": [{"type": "image_url"}]})
    assert progress.before(call) is None
    progress.evidence["s"]["revision"] = "new"
    assert progress.before(call) is not None


def test_revision_identity_ignores_fresh_native_and_transport_ids():
    from uuid import uuid4
    from app.mcp.office_word import WordEdits
    from app.mcp.office_contracts import ReadArguments
    xml = '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document><w:body><w:p w:rsidR="1"><w:r><w:t>A</w:t></w:r></w:p></w:body></w:document></pkg:xmlData></pkg:part></pkg:package>'
    document = SimpleNamespace(Content=SimpleNamespace(WordOpenXML=xml))
    edits = WordEdits(SimpleNamespace(documents={"doc": ("word", document)}))
    edits.read = lambda args, binding: {"session": "s", "snapshot": uuid4().hex, "cursor": None, "items": []}
    binding = {"document": {"document": "doc"}}
    arguments = ReadArguments(session="s", target="authoring")
    first = edits.reviewed_call("office.read", arguments, binding)
    document.Content.WordOpenXML = xml.replace('rsidR="1"', 'rsidR="2"')
    second = edits.reviewed_call("office.read", arguments, binding)
    assert first["snapshot"] != second["snapshot"]
    assert first["word_workflow"]["revision"] == second["word_workflow"]["revision"]
    document.Content.WordOpenXML = xml.replace(">A<", ">B<")
    changed = edits.reviewed_call("office.read", arguments, binding)
    assert changed["word_workflow"]["revision"] != first["word_workflow"]["revision"]
    document.Content.WordOpenXML = xml.replace('rsidR="1"', 'rsidR="3"')
    returned = edits.reviewed_call("office.read", arguments, binding)
    assert returned["word_workflow"]["revision_repeated"]


def test_failed_initial_word_write_cannot_be_reported_complete():
    from app.agent.word_evidence import WordTurnProgress
    from app.inference.protocol import ModelCapabilityCall
    from app.capabilities.contracts import CapabilityErrorCode
    progress = WordTurnProgress()
    call = ModelCapabilityCall(provider_call_id="compose", capability="office.word_compose", arguments={"session": "s"})
    progress.observe(call, SimpleNamespace(success=False, output=None,
        error=SimpleNamespace(code=CapabilityErrorCode.INVALID_ARGUMENTS)))
    retry, message = progress.before_final()
    assert retry and "unfinished" in message
    assert progress.before_final()[0] is False


def test_completion_requires_save_after_clean_review_and_noop_compose_cannot_restart():
    w = WordWorkflow(); w.sync("initial"); w.composed = True
    with pytest.raises(OfficeConflict, match="concrete"):
        w.before_edit()
    w.save("before-review")
    review(w)
    assert w.evidence()["current_save"]["operation"] == "before-review"
    assert not w.evidence()["verified_saved"]
    w.save("after-review")
    assert w.evidence()["verified_saved"]


def test_save_receipt_does_not_advertise_invalidated_authoring_authority():
    from app.mcp.office_word import WordEdits
    xml = '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage"/>'
    document = SimpleNamespace(Content=SimpleNamespace(WordOpenXML=xml))
    edits = WordEdits(SimpleNamespace(documents={"doc": ("word", document)}))
    edits.execute = lambda *args: {"session": "s", "operation": "save", "saved": True}
    binding = {"document": {"document": "doc"}}
    edits.workflow(binding).authoring = {"snapshot": "old", "revision": edits.workflow(binding).revision}
    receipt = edits.reviewed_call("office.save", SimpleNamespace(session="s"), binding, {}, "save")
    assert receipt["saved"]
    assert receipt["word_workflow"]["authoring_snapshot"] is None
    assert receipt["word_workflow"]["current_save"]["operation"] == "save"


def test_post_save_evidence_failure_retains_the_successful_receipt():
    from app.mcp.office_word import WordEdits
    from unittest.mock import Mock
    document = SimpleNamespace(Content=SimpleNamespace(WordOpenXML="unused"))
    edits = WordEdits(SimpleNamespace(documents={"doc": ("word", document)}))
    w = WordWorkflow(); w.sync("before-save")
    edits.workflow = Mock(side_effect=[w, RuntimeError("private native details")])
    edits.execute = lambda *args: {"session": "s", "operation": "saved", "saved": True}
    result = edits.reviewed_call("office.save", SimpleNamespace(session="s"),
        {"document": {"document": "doc"}}, {}, "saved")
    assert result["saved"]
    evidence = result["word_workflow"]
    assert evidence["current_save"] is None and not evidence["verified_saved"]
    assert evidence["save_receipts"] == [{"revision": None, "operation": "saved"}]
    assert evidence["blocker"] and "private" not in str(evidence)
