"""Full workbook discovery, paged coverage and premature completion regression."""
import json
import os
from types import SimpleNamespace as NS

import pytest

from app.agent.contracts import AgentRunStatus
from app.agent.office_read_progress import OfficeReadProgress
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.mcp.office_com import ExcelCells, OfficeUnavailable, WindowsOffice
from app.mcp.office_contracts import ReadArguments, excel_range_shape
from app.settings.agent import AgentRuntimeLimits
from tests.test_agent_runtime import ScriptedModel
from tests.test_office_mcp_excel import service, read, connection
from tests.test_office_mcp_capabilities import runtime_for
from tests.test_office_mcp_live import execute, tool
from tests.test_office_mcp_connection import ROOT


def test_native_discovery_quotes_sheet_names_and_freezes_large_used_ranges_lazily():
    sheet = NS(Name="Orders' 2026", UsedRange=NS(Row=5, Column=3,
        Rows=NS(Count=100_000), Columns=NS(Count=8), Address="$C$5:$J$100004"))
    document = NS(Worksheets=NS(Count=1, Item=lambda name: sheet))
    backend = WindowsOffice.__new__(WindowsOffice)
    backend.check_thread = lambda: None
    metadata = backend.plan("excel", document, "workbook")
    piece, cursor = backend.piece(metadata[0], 0, 8192)
    result = json.loads(piece["text"])
    assert cursor is None and result == {"sheet": "Orders' 2026", "used_range": "$C$5:$J$100004",
        "read_target": "'Orders'' 2026'!used", "objects_target": "'Orders'' 2026'!objects", "rows": 100_000, "columns": 8}
    plan = backend.plan("excel", document, result["read_target"])
    assert isinstance(plan, ExcelCells) and len(plan) == 800_000
    assert plan[0] == ("cell", sheet, 5, 3) and plan[-1 + len(plan)] == ("cell", sheet, 100004, 10)
    with pytest.raises(IndexError):
        plan[len(plan)]
    with pytest.raises(ValueError):
        excel_range_shape("A1:H128")  # Explicit patch/read rectangles keep their existing bound.


@pytest.mark.parametrize("rows", [36, 128])
def test_full_used_range_pages_include_every_cell_past_row_15_and_patch_limit(rows):
    live, authority, session = service()
    try:
        for r in range(1, rows + 1):
            for c in range(1, 9):
                live.backend.sheets["Sheet1"][(r, c)] = {"value": r * 10 + c, "formula": "",
                    "number_format": "General", "bold": False, "italic": False}
        metadata = read(live, authority, session, target="workbook")
        assert json.loads(metadata["items"][0]["text"])["rows"] == rows
        cursor, seen, snapshots, pages = None, {}, set(), 0
        while True:
            output = read(live, authority, session, target="'Sheet1'!used", cursor=cursor)
            tool("read").validate_result(ReadArguments(session=session, target="'Sheet1'!used", cursor=cursor), output)
            snapshots.add(output["snapshot"])
            pages += 1
            for item in output["items"]:
                for row in item["values"]:
                    for value in row:
                        assert value not in seen
                        seen[value] = value
            cursor = output["cursor"]
            if cursor is None:
                break
        assert len(seen) == rows * 8 and rows * 10 + 8 in seen
        assert len(snapshots) == 1 and pages == (rows * 8 + 99) // 100
        assert len(live.snapshots[next(iter(snapshots))][2]) == rows * 8
        assert live.backend.writes == 0
    finally:
        live.close()


def test_used_range_growth_invalidates_continuation_instead_of_missing_new_rows():
    live, authority, session = service()
    try:
        live.backend.sheets["Sheet1"][(36, 8)] = {"value": 1, "formula": "", "number_format": "General",
                                                   "bold": False, "italic": False}
        page = read(live, authority, session, target="Sheet1!used")
        live.backend.sheets["Sheet1"][(37, 8)] = dict(live.backend.sheets["Sheet1"][(36, 8)])
        with pytest.raises(OfficeUnavailable, match="used range changed"):
            read(live, authority, session, target="Sheet1!used", cursor=page["cursor"])
    finally:
        live.close()


def test_full_read_failure_stays_unfinished_but_explicit_preview_does_not_force_more_reads():
    progress = OfficeReadProgress()
    preview = NS(capability="office.read", arguments={"session": "s", "target": "Sheet1!A1:H15"})
    progress.observe(preview, NS(success=True, output={"cursor": "next"}))
    assert progress.before_final() is None
    full = NS(capability="office.read", arguments={"session": "s", "target": "Sheet1!used"})
    progress.observe(full, NS(success=True, output={"cursor": "next"}))
    assert progress.before_final()[0] is True
    assert progress.before_final()[0] is False
    progress.observe(full, NS(success=False, error=NS(message="Read permission denied.")))
    retry, message = progress.before_final()
    assert not retry and "permission denied" in message
    progress.observe(full, NS(success=True, output={"cursor": None}))
    assert progress.before_final() is None
    # An initial malformed request must not leave a permanent blocker after the
    # model corrects its session or uses the proper target for another application.
    wrong = NS(capability="office.read", arguments={"session": "wrong", "target": "workbook"})
    progress.observe(wrong, NS(success=False, error=NS(message="Unknown session.")))
    assert progress.before_final() is None


class PagingModel(ScriptedModel):
    def __init__(self, session, *, stall=False):
        super().__init__([])
        self.mode, self.context_length = "cloud", 131_072
        self.session, self.stall, self.early = session, stall, False
        self.pages = 0

    def respond_with_capabilities(self, messages, capabilities):
        outputs = [m["result"]["output"] for m in messages if m.get("role") == "capability"
                   and m.get("result", {}).get("capability") == "office.read"]
        if not outputs:
            result = ModelResponse.calls((ModelCapabilityCall(provider_call_id="full-read",
                capability="office.read", arguments={"session": self.session, "target": "'Sheet1'!used"}),))
        elif outputs[-1].get("cursor"):
            if not self.early or self.stall:
                self.early = True
                result = ModelResponse.text("All workbook data has been read.")
            else:
                self.pages += 1
                result = ModelResponse.calls((ModelCapabilityCall(provider_call_id="page" + str(self.pages),
                    capability="office.read", arguments={"session": self.session, "target": "'Sheet1'!used",
                                                         "cursor": outputs[-1]["cursor"]}),))
        else:
            result = ModelResponse.text("All 36 rows have been read.")
        self.responses.append(result)
        return super().respond_with_capabilities(messages, capabilities)


@pytest.mark.skipif(os.name != "nt", reason="Windows owned SDK/stdio integration")
@pytest.mark.parametrize("stall", [False, True])
def test_actual_runtime_does_not_settle_a_premature_full_workbook_answer(tmp_path, stall):
    bridge = connection()
    model = PagingModel("pending", stall=stall)
    runtime = runtime_for(bridge, tmp_path, model=model, policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        bridge.control("fixture-cells", {"sheet": "Sheet1", "values": [[r * 10 + c for c in range(8)] for r in range(36)]})
        attached = execute(runtime, "attach", {"application": "excel", "document": document["document"]}, "attach")
        model.session = attached.output["session"]
        result = runtime.run([{"role": "system", "content": "Read the complete attached workbook."},
                              {"role": "user", "content": "Read the complete attached workbook."}],
            session_id="full-read-session", turn_id="full-read-turn", portable_root=ROOT,
            allowed_read_roots=(ROOT,))
        assert model.early
        if stall:
            assert result.status == AgentRunStatus.INCOMPLETE and "unfinished" in result.partial_text
            assert bridge.diagnostics["tool_calls"] == 2  # attach + first read; no automatic dispatch
        else:
            assert result.status == AgentRunStatus.COMPLETED and result.assistant_text == "All 36 rows have been read."
            assert model.pages == 2 and bridge.diagnostics["tool_calls"] == 4
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


@pytest.mark.skipif(os.name != "nt", reason="Windows owned SDK/stdio integration")
def test_unsupported_office_edits_report_the_real_cause_without_weakening_semantic_budget(tmp_path):
    bridge = connection()
    model = ScriptedModel([])
    model.mode, model.context_length = "cloud", 131_072
    runtime = runtime_for(bridge, tmp_path, model=model, policy=bridge.resource_policy)
    runtime.limits = AgentRuntimeLimits(max_semantic_corrections=2)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime, "attach", {"application": "excel", "document": document["document"]}, "attach").output["session"]
        snapshot = execute(runtime, "read", {"session": session, "target": "Sheet1!A1:A2"}, "read").output["snapshot"]
        for i in (1, 2):
            model.responses.append(ModelResponse.calls((ModelCapabilityCall(provider_call_id="unsupported" + str(i),
                capability="office.excel_edit", arguments={"session": session, "snapshot": snapshot,
                    "changes": [{"sheet": "Sheet1", "range": "A" + str(i), "formulas": [["=[outside.xlsx]Other!A1"]]}]}),)))
        result = runtime.run([{"role": "system", "content": "Use the supported tools."},
            {"role": "user", "content": "Update the workbook."}], session_id="semantic-session",
            turn_id="semantic-turn", portable_root=ROOT, allowed_read_roots=(ROOT,))
        assert result.status == AgentRunStatus.SEMANTIC_CORRECTION_LIMIT and result.semantic_corrections == 2
        assert "office.excel_edit" in result.message and "supported local Excel subset" in result.message
        assert bridge.diagnostics["tool_calls"] == 2  # Both mutations rejected before dispatch/approval.
    finally:
        runtime.shutdown()
