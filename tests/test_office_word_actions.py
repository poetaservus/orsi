"""Focused pending Word actions: full coverage, authority, preservation and recovery."""
from copy import deepcopy
import json

import pytest

from app.capabilities.contracts import CapabilityExecutionError
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_word_tables import table_replacement
from tests.test_office_mcp_word import service, read, mutate, connection
from tests.test_office_mcp_live import tool, execute
from tests.test_office_mcp_capabilities import runtime_for, prepare


PAYLOADS = {"insert_after": {"text": " after \U0001f642"}, "apply_style": {"style": "Heading 1"},
            "edit_table": {"cells": [["Longer <&>", "Two"], ["Three", "new\U0001f642"]]}}


def page(live, authority, session, action, **kwargs):
    return live.call(tool("read"), tool("read").arguments(session=session,
        target="table:1" if action == "edit_table" else "document", **kwargs), authority)


def arguments(session, view, action, **payload):
    return {"session": session, "snapshot": view["snapshot"], "changes": [
        {"target": view["items"][0]["target"], "action": action, **(payload or PAYLOADS[action])}]}


@pytest.mark.parametrize("action", PAYLOADS)
def test_each_action_requires_complete_read_and_restores_owned_state(action):
    live, authority, session = service()
    original = (live.backend.docs[0]["value"], deepcopy(live.backend.style), deepcopy(live.backend.table))
    first = view = page(live, authority, session, action, max_chars=4)
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", arguments(session, first, action))
    while view["cursor"]:
        view = page(live, authority, session, action, cursor=view["cursor"], max_chars=4)
        assert view["snapshot"] == first["snapshot"]
        assert view["items"][0]["target"] == first["items"][0]["target"]
    edited = mutate(live, authority, "word_edit", arguments(session, first, action))
    assert edited["affected_items"] == (2 if action == "edit_table" else 1)
    after = page(live, authority, session, action)
    restored = mutate(live, authority, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited["recovery"]}, "restore")
    assert restored["outcome"] == "applied"
    assert original == (live.backend.docs[0]["value"], live.backend.style, live.backend.table)


@pytest.mark.parametrize("action", PAYLOADS)
def test_after_approval_foreign_changes_reject_before_dispatch(action):
    live, authority, session = service()
    args = tool("word_edit").arguments.model_validate(arguments(session, page(live, authority, session, action), action))
    guard = live.word.prepare("office.word_edit", args, live.binding(session=session))
    if action == "edit_table":
        live.backend.table["structure"] = ["changed by user"]
    else:
        live.backend.docs[0]["value"] = "changed by user"
    with pytest.raises(OfficeConflict):
        live.call(tool("word_edit"), args, {**authority, "guard": guard["guard"]}, "stale")
    assert live.backend.writes == 0 and not live.word.blocked


@pytest.mark.parametrize("action", PAYLOADS)
def test_recovery_refuses_later_edits_for_each_action(action):
    live, authority, session = service()
    edited = mutate(live, authority, "word_edit", arguments(session, page(live, authority, session, action), action))
    after = page(live, authority, session, action)
    if action == "edit_table":
        live.backend.table["cells"][3]["text"] = "later user edit"
    elif action == "apply_style":
        live.backend.style = None
    else:
        live.backend.docs[0]["value"] = "later user edit"
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited["recovery"]})
    assert live.backend.writes == 1


@pytest.mark.parametrize("action", PAYLOADS)
@pytest.mark.parametrize("mode", ["partial", "miswrite"])
def test_each_uncertain_action_blocks_without_automatic_rollback(action, mode):
    live, authority, session = service(mode)
    with pytest.raises(OfficeUnknown):
        mutate(live, authority, "word_edit", arguments(session, page(live, authority, session, action), action))
    assert live.word.blocked and live.backend.writes == 1
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", arguments(session, page(live, authority, session, action), action))
    assert live.backend.writes == 1


def test_table_matrix_shape_markers_mixed_runs_and_metadata_do_not_authorize_writes():
    live, authority, session = service()
    initial = page(live, authority, session, "edit_table")
    value = json.loads(initial["items"][0]["text"])
    assert value["rows"] == value["columns"] == 2 and len(value["cell_ranges"]) == 4
    for cells in ([["wrong shape"]], [["One\r", "Two"], ["Three", ""]]):
        with pytest.raises(OfficeConflict):
            mutate(live, authority, "word_edit", arguments(session, initial, "edit_table", cells=cells))
    live.backend.table["cells"][0]["paragraph"][2] = [[None, "O"], [["rPr", {}, "", []], "ne"]]
    mixed = page(live, authority, session, "edit_table")
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", arguments(session, mixed, "edit_table"))
    allowed = table_replacement(live.backend.table, [["One", "changed"], ["Three", ""]])
    assert allowed["cells"][0] == live.backend.table["cells"][0]
    metadata = live.call(tool("read"), tool("read").arguments(session=session, target="tables"), authority)
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", arguments(session, metadata, "edit_table"))
    assert live.backend.writes == 0


def test_style_requires_discovered_name_and_complete_paragraph_and_insert_is_bounded():
    live, authority, session = service()
    full = read(live, authority, session)
    for payload in ({"style": "Arbitrary unsupported style"}, {"style": "Heading 1", "text": "wrong"}):
        with pytest.raises((OfficeConflict, ValueError)):
            mutate(live, authority, "word_edit", arguments(session, full, "apply_style", **payload))
    short = live.call(tool("read"), tool("read").arguments(session=session, target="text:0:3"), authority)
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", arguments(session, short, "apply_style"))
    for text in ("", "x\n", "\U0001f642" * 2048):
        with pytest.raises(OfficeConflict):
            mutate(live, authority, "word_edit", arguments(session, full, "insert_after", text=text))
    assert live.backend.writes == 0


def test_style_gallery_usage_is_distinct_from_formatting_definition_changes():
    from app.mcp.office_word_native import dependencies
    xml = ('<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<pkg:part pkg:name="/word/styles.xml"><pkg:xmlData><w:styles>'
           '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
           '<w:semiHidden/><w:link w:val="Heading2Char"/><w:rPr><w:sz w:val="24"/></w:rPr>'
           '</w:style></w:styles></pkg:xmlData></pkg:part></pkg:package>')
    assert dependencies(xml) == dependencies(xml.replace('<w:semiHidden/>', ''))
    assert dependencies(xml) != dependencies(xml.replace('w:val="24"', 'w:val="28"'))
    assert dependencies(xml) != dependencies(xml.replace('w:val="Heading2Char"', 'w:val="OtherChar"'))


@pytest.mark.parametrize("action", PAYLOADS)
def test_actual_stdio_action_restore_and_journal(action, tmp_path):
    bridge = connection()
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "word", "document": document["document"]}, "attach").output["session"]
        target = "table:1" if action == "edit_table" else "document"
        initial = execute(runtime, "read", {"session": session, "target": target}, "read").output
        edited = execute(runtime, "word_edit", arguments(session, initial, action), "edit")
        assert edited.success
        after = execute(runtime, "read", {"session": session, "target": target}, "after").output
        assert execute(runtime, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited.output["recovery"]}, "restore").success
        assert "Longer" not in (tmp_path / "capability_journal_v1.json").read_text()
        assert runtime.model.calls == 0
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]
