"""Essential Word coverage, authority, preservation and uncertainty checks."""
import sys

import pytest

from app.capabilities.contracts import CapabilityExecutionError
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_discovery import OfficeDiscovery, OfficeInstallation
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_live import LiveOffice
from app.mcp.office_word_native import replacement, slice_units
from app.mcp.stdio_transport import OwnedStdioTransport
from tests.fixtures.office_word_server import MemoryWord
from tests.test_office_mcp_capabilities import runtime_for, prepare
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_live import tool, execute


def service(mode="normal"):
    live = LiveOffice(lambda: MemoryWord(mode))
    live.control("configure", {"applications": ["word"]})
    document = next(iter(live.documents))
    binding = live.binding(document=document)
    authority = {"document": document, "identity": binding["identity"]}
    attached = live.call(tool("attach"), tool("attach").arguments(application="word", document=document), authority)
    return live, authority, attached["session"]


def read(live, authority, session, **kwargs):
    return live.call(tool("read"), tool("read").arguments(session=session, target="document", **kwargs), authority)


def patch(session, page, text="replacement\U0001f642"):
    return {"session": session, "snapshot": page["snapshot"], "changes": [
        {"target": page["items"][0]["target"], "action": "replace_text", "text": text}]}


def mutate(live, authority, name, args, operation="edit"):
    arguments = tool(name).arguments.model_validate(args)
    guard = live.word.prepare("office." + name, arguments, live.binding(session=arguments.session))
    return live.call(tool(name), arguments, {**authority, "guard": guard["guard"]}, operation)


def test_complete_paged_unicode_target_restores_and_refuses_later_changes():
    live, authority, session = service()
    first = page = read(live, authority, session, max_chars=2)
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", patch(session, first))
    while page["cursor"]:
        page = read(live, authority, session, cursor=page["cursor"], max_chars=2)
        assert page["snapshot"] == first["snapshot"]
        assert page["items"][0]["target"] == first["items"][0]["target"]
    edited = mutate(live, authority, "word_edit", patch(session, first))
    after = read(live, authority, session)
    live.backend.docs[0]["value"] = "later user change"
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited["recovery"]})
    live.backend.docs[0]["value"] = "replacement\U0001f642"
    after = read(live, authority, session)
    restored = mutate(live, authority, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited["recovery"]}, "restore")
    assert restored["affected_items"] == 1 and live.backend.docs[0]["value"] == "alpha\U0001f642 beta"
    assert live.backend.writes == 2


@pytest.mark.parametrize("change", ["earlier_page", "format", "anchor"])
def test_any_earlier_fragment_format_or_anchor_change_refuses_continuation(change):
    live, authority, session = service()
    first = read(live, authority, session, max_chars=2)
    if change == "earlier_page":
        live.backend.docs[0]["value"] = "XXpha\U0001f642 beta"
    elif change == "format":
        live.backend.props = None
    else:
        live.backend.anchors[0]["start"] += 1
    with pytest.raises(OfficeConflict):
        read(live, authority, session, cursor=first["cursor"], max_chars=2)
    assert live.backend.writes == 0


@pytest.mark.parametrize("change", ["text", "format", "anchor", "readonly"])
def test_approval_consumes_exact_authority_and_rechecks_before_writing(change):
    live, authority, session = service()
    args = tool("word_edit").arguments.model_validate(patch(session, read(live, authority, session)))
    guard = live.word.prepare("office.word_edit", args, live.binding(session=session))
    if change == "text":
        live.backend.docs[0]["value"] = "different"
    elif change == "format":
        live.backend.props = None
    elif change == "anchor":
        live.backend.anchors[0]["start"] += 1
    else:
        live.backend.docs[0]["readonly"] = True
    with pytest.raises(OfficeConflict):
        live.call(tool("word_edit"), args, {**authority, "guard": guard["guard"]}, "edit")
    assert live.backend.writes == 0 and not live.word.blocked
    with pytest.raises(OfficeConflict):
        live.call(tool("word_edit"), args, {**authority, "guard": guard["guard"]}, "replay")


@pytest.mark.parametrize("mode", ["partial", "miswrite"])
def test_partial_or_misverified_word_write_blocks_without_rollback(mode):
    live, authority, session = service(mode)
    with pytest.raises(OfficeUnknown) as error:
        mutate(live, authority, "word_edit", patch(session, read(live, authority, session)))
    assert "SECRET" not in str(error.value)
    assert live.word.blocked and live.backend.writes == 1
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", patch(session, read(live, authority, session)))
    assert live.backend.writes == 1


def test_unicode_semantic_replacement_preserves_mixed_surrounding_runs():
    live, authority, session = service()
    doc = live.backend.docs[0]
    state = live.backend.capture_word(live.backend.word_descriptor(doc, 5, 7))
    plain, bold = None, ["rPr", {}, "", []]
    state["target"][2] = [[plain, "\U0001f642"]]
    state["paragraph"][2] = [[bold, "alpha"], [plain, "\U0001f642 beta"]]
    updated = replacement(state, "longer\U0001f642")
    assert updated["paragraph"][2] == [[bold, "alpha"], [plain, "longer\U0001f642 beta"]]
    assert updated["end"] == 13 and updated["pend"] - state["pend"] == 6
    with pytest.raises(OfficeConflict):
        slice_units("\U0001f642", 0, 1)
    for text in ("", "x\r", "x\x07", "x\n", "x\t", "\U0001f642" * 2049):
        with pytest.raises(OfficeConflict):
            replacement(state, text)


def test_replacement_keeps_inherited_paragraph_runs_separate_from_materialized_range_fonts():
    live, authority, session = service()
    state = live.backend.capture_word(live.backend.plan("word", live.backend.docs[0], "document")[0])
    state["paragraph"][2][0][0] = None  # Inherited fonts in the complete paragraph export.
    updated = replacement(state, "changed")
    assert updated["paragraph"][2] == [[None, "changed"]]
    assert updated["target"][2][0][0] == state["target"][2][0][0]


def test_wrong_payloads_multiple_changes_and_cross_application_edits_reject():
    live, authority, session = service()
    page = read(live, authority, session)
    for action in ("apply_style", "edit_table"):
        args = patch(session, page)
        args["changes"][0]["action"] = action
        with pytest.raises(ValueError):
            tool("word_edit").arguments.model_validate(args)
    args = patch(session, page)
    args["changes"] *= 2
    with pytest.raises(ValueError):
        tool("word_edit").arguments.model_validate(args)
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "excel_edit", {"session": session, "snapshot": page["snapshot"],
            "changes": [{"sheet": "Sheet1", "range": "A1", "values": [[2]]}]})
    assert live.backend.writes == 0


def connection(mode="normal"):
    return OfficeConnection(ROOT, backend=lambda: "cloud",
        discovery=OfficeDiscovery(lambda: (OfficeInstallation("word", "fixture", None),)),
        _transport_factory=lambda: OwnedStdioTransport([sys.executable, "-m", "tests.fixtures.office_word_server", mode], root=ROOT))


def test_production_stdio_permissions_recovery_and_unknown_journal(tmp_path):
    from app.security.write_policy import HostWritePolicy
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        bridge.connect()
        assert {n for n in runtime.registry.model_visible_names if n.startswith("office.")} == {
            "office.documents", "office.attach", "office.read", "office.word_edit", "office.word_compose", "office.revert", "office.save"}
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        page = execute(runtime, "read", {"session": session, "target": "document"}, "read").output
        edited = execute(runtime, "word_edit", patch(session, page), "edit")
        assert edited.success
        after = execute(runtime, "read", {"session": session, "target": "document"}, "after").output
        assert execute(runtime, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited.output["recovery"]}, "restore").success
        (tmp_path / "application").mkdir()
        runtime.registry.resolve("office.save").write_policy = HostWritePolicy(tmp_path / "application")
        path = tmp_path / "synthetic.docx"
        assert execute(runtime, "save", {"session": session, "path": str(path)}, "save-as").success
        assert execute(runtime, "save", {"session": session}, "save").success
        assert execute(runtime, "read", {"session": session}, "new-binding").success
        assert "replacement" not in (tmp_path / "capability_journal_v1.json").read_text()
        assert runtime.model.calls == 0
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


def test_stdio_partial_write_is_outcome_unknown_and_has_no_retry(tmp_path):
    from app.capabilities.contracts import CapabilityErrorCode
    bridge = connection("partial")
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        page = execute(runtime, "read", {"session": session}, "read").output
        result = execute(runtime, "word_edit", patch(session, page), "edit")
        assert not result.success and result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN
        assert bridge.diagnostics["tool_calls"] == 3
        assert not bridge.exposure.ready
        assert runtime.executor.journal.review_required
        assert "SECRET" not in (tmp_path / "capability_journal_v1.json").read_text()
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("legacy_action", ["replace_text", "apply_style", "insert_after", "edit_table"])
def test_original_word_history_replays_exactly_but_does_not_expand_live_schema(legacy_action):
    from copy import deepcopy
    from app.inference.openai_tools import _arguments, normalize_responses_calls, responses_function_tools, responses_input
    from app.inference.completion import CompletionMetadata
    from app.mcp.office_contracts import OfficeExposure, office_catalog
    from tests.test_openai_replay import evidence, history_for
    from tests.test_openai_tools import function
    definitions = office_catalog(OfficeExposure(backend="cloud", enabled=True, ready=True, generation=1)).model_definitions()
    current = next(d for d in definitions if d.name == "office.word_edit")
    schema = deepcopy(current.input_schema)
    action = schema["$defs"]["WordChange"]["properties"]["action"]
    action.pop("const", None)
    action["enum"] = ["replace_text", "insert_after", "apply_style", "edit_table"]
    schema["properties"]["changes"]["maxItems"] = 16
    legacy = current.model_copy(update={"input_schema": schema})
    payload = ({"style": "Heading 1"} if legacy_action == "apply_style" else
               {"cells": [["table"]]} if legacy_action == "edit_table" else {"text": "replacement"})
    arguments = {"session": "s", "snapshot": "r", "changes": [{"target": "p", "action": legacy_action, **payload}]}
    wire = _arguments(schema, arguments, schema, from_wire=False)
    output = [function(legacy, wire)]
    replay = evidence(output)
    response = normalize_responses_calls(output, (legacy,), CompletionMetadata())
    history = [{"role": "user", "content": "Synthetic historical Word edit"}, *history_for(replay, response.capability_calls)]
    projected = responses_input(history, definitions)
    assert projected[1] == output[0]
    live_action = responses_function_tools((current,))[0]["parameters"]["$defs"]["WordChange"]["properties"]["action"]
    assert live_action["enum"] == ["replace_text", "insert_after", "apply_style", "edit_table"]
