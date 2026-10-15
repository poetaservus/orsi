"""Essential Excel conflict, recovery, exact approval and uncertainty gates."""
from pathlib import Path
import sys
from threading import Timer

import pytest

from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_discovery import OfficeDiscovery, OfficeInstallation
from app.mcp.office_excel import OfficeConflict, OfficeUnknown, validate_formula, formula_key
from app.mcp.office_live import LiveOffice
from app.mcp.stdio_transport import OwnedStdioTransport
from app.runtime.cancellation import CancellationSource
from app.security.permissions import ApprovalStatus
from tests.fixtures.office_excel_server import MemoryExcel
from tests.test_office_mcp_capabilities import runtime_for, prepare, authorize
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_live import tool, execute


def service(mode="normal"):
    live = LiveOffice(lambda: MemoryExcel(mode))
    live.control("configure", {"applications": ["excel"]})
    document = next(iter(live.documents))
    bound = live.binding(document=document)
    authority = {"document": document, "identity": bound["identity"]}
    attached = live.call(tool("attach"), tool("attach").arguments(application="excel", document=document), authority)
    return live, authority, attached["session"]


def read(live, authority, session, target="Sheet1!A1:A2", **kwargs):
    return live.call(tool("read"), tool("read").arguments(session=session, target=target, **kwargs), authority)


def mutate(live, authority, name, arguments, operation="edit"):
    arguments = tool(name).arguments.model_validate(arguments)
    binding = live.binding(session=arguments.session)
    guard = live.excel.prepare("office." + name, arguments, binding)
    return live.call(tool(name), arguments, {**authority, "guard": guard["guard"]}, operation)


def patch(session, snapshot, **payload):
    return {"session": session, "snapshot": snapshot, "changes": [{"sheet": "Sheet1", "range": "A1:A2", **payload}]}


def test_values_formulas_formats_restore_exactly_and_refuse_later_changes():
    live, authority, session = service()
    snapshot = read(live, authority, session)["snapshot"]
    edited = mutate(live, authority, "excel_edit", patch(session, snapshot, values=[["=literal"], [7]],
                     bold=True, italic=True, number_format="0.00"))
    assert edited["affected_items"] == 2
    after = read(live, authority, session)
    assert after["items"][0]["values"] == [["=literal"]]
    assert after["items"][0]["formulas"] == [[""]]
    restored = mutate(live, authority, "revert", {"session": session, "snapshot": after["snapshot"], "recovery": edited["recovery"]}, "restore")
    assert restored["affected_items"] == 2
    current = read(live, authority, session)
    assert current["items"][0]["values"] == [[None]]
    mutated = mutate(live, authority, "excel_edit", patch(session, current["snapshot"], formulas=[["=2+3"], ["=2+3"]]), "formula")
    current = read(live, authority, session)
    live.backend.sheets["Sheet1"][(1, 1)]["value"] = 99
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "revert", {"session": session, "snapshot": current["snapshot"], "recovery": mutated["recovery"]})
    assert live.backend.sheets["Sheet1"][(1, 1)]["value"] == 99


def test_paged_snapshot_accumulates_cell_coverage_and_long_string_fragments():
    live, authority, session = service()
    live.backend.sheets["Sheet1"][(1, 1)] = {"value": "x" * 3000, "formula": "", "number_format": "General", "bold": False, "italic": False}
    page = read(live, authority, session, max_chars=100)
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "excel_edit", patch(session, page["snapshot"], values=[[1], [2]]))
    snapshot = page["snapshot"]
    while page["cursor"]:
        page = read(live, authority, session, cursor=page["cursor"], max_chars=100)
        assert page["snapshot"] == snapshot
    assert mutate(live, authority, "excel_edit", patch(session, snapshot, values=[[1], [2]]))["affected_items"] == 2


@pytest.mark.parametrize("change", [{"value": 8}, {"number_format": "@"}, {"bold": True}, {"italic": True}])
def test_prepared_patch_rechecks_all_expected_cell_state_before_any_write(change):
    live, authority, session = service()
    snapshot = read(live, authority, session)["snapshot"]
    arguments = tool("excel_edit").arguments.model_validate(patch(session, snapshot, values=[[1], [2]]))
    guard = live.excel.prepare("office.excel_edit", arguments, live.binding(session=session))
    state = live.backend.capture_excel(live.backend.plan("excel", None, "Sheet1!A2")[0])
    state.update(change)
    live.backend.sheets["Sheet1"][(2, 1)] = state
    with pytest.raises(OfficeConflict):
        live.call(tool("excel_edit"), arguments, {**authority, "guard": guard["guard"]}, "edit")
    assert live.backend.writes == 0


@pytest.mark.parametrize("mode", ["partial", "miswrite"])
def test_partial_or_unverified_write_blocks_future_mutations_without_rollback(mode):
    live, authority, session = service(mode)
    snapshot = read(live, authority, session)["snapshot"]
    with pytest.raises(OfficeUnknown):
        mutate(live, authority, "excel_edit", patch(session, snapshot, values=[[1], [2]]))
    assert live.excel.blocked
    assert live.backend.sheets["Sheet1"][(1, 1)]["value"] == 1
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "excel_edit", patch(session, snapshot, values=[[3], [4]]))


@pytest.mark.parametrize("formula", ['=WEBSERVICE("https://example.test")', '=SomeName', '=myUdf(A1)', "='other'!A1", '=[book]Sheet1!A1', '=cmd|x!A1'])
def test_initial_formula_subset_rejects_external_automation(formula):
    with pytest.raises(OfficeConflict):
        validate_formula(formula)


def test_formula_verification_preserves_string_case_and_accepts_absolute_references():
    validate_formula('=IF($A$1>0,"UPPER","lower")')
    assert formula_key('=sum(A1:A2)') == formula_key('=SUM(A1:A2)')
    assert formula_key('="UPPER"') != formula_key('="upper"')


def test_boolean_to_numeric_changes_are_writes_and_later_type_changes_conflict():
    live, authority, session = service()
    mutate(live, authority, "excel_edit", patch(session, read(live, authority, session)["snapshot"], values=[[True], [False]]))
    result = mutate(live, authority, "excel_edit", patch(session, read(live, authority, session)["snapshot"], values=[[1], [0]]), "numeric")
    assert result["affected_items"] == 2
    snapshot = read(live, authority, session)["snapshot"]
    live.backend.sheets["Sheet1"][(1, 1)]["value"] = True
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "excel_edit", patch(session, snapshot, bold=True))


def test_empty_literals_clear_cells_and_oversized_integers_fail_before_writing():
    live, authority, session = service()
    result = mutate(live, authority, "excel_edit", patch(session, read(live, authority, session)["snapshot"], values=[[""], [None]]))
    assert result["outcome"] == "unchanged" and live.backend.writes == 0
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "excel_edit", patch(session, read(live, authority, session)["snapshot"], values=[[10**18], [None]]))
    assert live.backend.writes == 0


def test_a_write_invalidates_continuations_of_its_consumed_snapshot():
    live, authority, session = service()
    page = read(live, authority, session, max_items=1)
    assert page["cursor"]
    mutate(live, authority, "excel_edit", {"session": session, "snapshot": page["snapshot"],
           "changes": [{"sheet": "Sheet1", "range": "A1", "values": [[1]]}]})
    with pytest.raises(Exception, match="cursor"):
        read(live, authority, session, cursor=page["cursor"])


def connection(mode="normal", **kwargs):
    return OfficeConnection(ROOT, backend=lambda: "cloud", discovery=OfficeDiscovery(lambda:
        (OfficeInstallation("excel", "fixture", None),)), _transport_factory=lambda:
        OwnedStdioTransport([sys.executable, "-m", "tests.fixtures.office_excel_server", mode], root=ROOT), **kwargs)


def start(bridge, tmp_path):
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    bridge.connect()
    document = bridge.list_documents()[0]
    bridge.select_document(document["document"])
    attached = execute(runtime, "attach", {"application": "excel", "document": document["document"]}, "attach")
    session = attached.output["session"]
    result = execute(runtime, "read", {"session": session, "target": "Sheet1!A1:A2"}, "read")
    return runtime, session, result.output["snapshot"]


def test_real_stdio_denied_approval_and_changed_target_never_dispatch_patch(tmp_path):
    bridge = connection()
    runtime, session, snapshot = start(bridge, tmp_path)
    try:
        prepared = prepare(runtime, "office.excel_edit", patch(session, snapshot, values=[[1], [2]]), "denied")
        authorization = authorize(runtime, prepared, ApprovalStatus.DENIED)
        assert not authorization.allowed
        assert not runtime.executor.executor.execute(prepared, authorization).success
        assert bridge.diagnostics["tool_calls"] == 2
        prepared = prepare(runtime, "office.excel_edit", patch(session, snapshot, values=[[1], [2]]), "changed")
        auth = authorize(runtime, prepared)
        bridge.control("fixture", {"target": "Sheet1!A2", "change": {"value": 9}})
        result = runtime.executor.execute(prepared, auth)
        assert not result.success and "conflict" in result.error.message.lower()
        assert bridge.exposure.ready and not runtime.executor.review_required
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("required", [True, False])
def test_real_agent_preserves_approval_on_off_and_exact_call_consumption(tmp_path, required):
    from app.inference.protocol import ModelCapabilityCall, ModelResponse
    from tests.test_agent_runtime import ScriptedModel
    bridge = connection()
    runtime, session, snapshot = start(bridge, tmp_path)
    model = ScriptedModel([ModelResponse.calls((ModelCapabilityCall(provider_call_id="excel-patch",
        capability="office.excel_edit", arguments=patch(session, snapshot, values=[[1], [2]])),)),
        ModelResponse.text("The synthetic cells were updated.")])
    model.mode = "cloud"
    runtime.model = model
    reviewed = []
    runtime.set_tool_approval_required(required)

    def approve(record):
        reviewed.append(record)
        runtime.resolve_approval(record.approval_id, True)

    runtime.set_approval_requester(approve)
    try:
        result = runtime.run([{"role": "user", "content": "Update the two synthetic Excel cells."}],
            session_id="session1", turn_id="turn-agent", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert result.status.value == "completed"
        assert len(reviewed) == int(required)
        assert len(runtime.approval_manager.records) == 1
        assert runtime.approval_manager.records[0].status == ApprovalStatus.CONSUMED
        assert bridge.diagnostics["tool_calls"] == 3
    finally:
        runtime.shutdown()


def test_cancelled_patch_never_prepares_or_dispatches_a_write(tmp_path):
    from app.runtime.cancellation import TaskCancelled
    bridge = connection()
    runtime, session, snapshot = start(bridge, tmp_path)
    source = CancellationSource()
    source.cancel()
    try:
        with pytest.raises(TaskCancelled):
            prepare(runtime, "office.excel_edit", patch(session, snapshot, values=[[1], [2]]), "cancel", source)
        assert bridge.diagnostics["tool_calls"] == 2 and not runtime.executor.review_required
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("mode", ["partial", "miswrite", "hang"])
def test_real_stdio_unknown_outcome_enters_existing_journal_gate(tmp_path, mode):
    bridge = connection(mode, call_timeout=1)
    runtime, session, snapshot = start(bridge, tmp_path)
    source = CancellationSource()
    timer = Timer(.1, source.cancel)
    try:
        prepared = prepare(runtime, "office.excel_edit", patch(session, snapshot, values=[[1], [2]]), "edit", source)
        auth = authorize(runtime, prepared)
        if mode == "hang":
            timer.start()
        result = runtime.executor.execute(prepared, auth)
        assert result.error.code == CapabilityErrorCode.OUTCOME_UNKNOWN
        assert runtime.executor.review_required
        assert "SECRET" not in result.error.message
    finally:
        timer.cancel()
        runtime.shutdown()


def test_real_stdio_success_recovery_and_save_as_use_existing_permissions(tmp_path):
    bridge = connection()
    runtime, session, snapshot = start(bridge, tmp_path)
    try:
        edited = execute(runtime, "excel_edit", patch(session, snapshot, values=[["=literal"], [2]]), "edit")
        assert edited.success and edited.output["recovery"]
        after = execute(runtime, "read", {"session": session, "target": "Sheet1!A1:A2"}, "after")
        restored = execute(runtime, "revert", {"session": session, "snapshot": after.output["snapshot"], "recovery": edited.output["recovery"]}, "restore")
        assert restored.success
        destination = tmp_path / "fixture.xlsx"
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.save", {"session": session, "path": str(destination)}, "protected-save")
        from app.security.write_policy import HostWritePolicy
        (tmp_path / "test-application").mkdir()
        runtime.registry.resolve("office.save").write_policy = HostWritePolicy(tmp_path / "test-application")
        saved = execute(runtime, "save", {"session": session, "path": str(destination)}, "save-as")
        assert saved.success and destination.is_file()
        assert "=literal" not in (tmp_path / "capability_journal_v1.json").read_text()
        # Exact Save As authority updates the selected resource without focus redirection.
        assert execute(runtime, "read", {"session": session, "target": "Sheet1!A1"}, "read-saved").success
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.save", {"session": session, "path": str(destination), "overwrite": True}, "replace")
    finally:
        runtime.shutdown()
