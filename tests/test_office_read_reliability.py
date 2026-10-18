"""Reproduced read deadline, normalized page size and native guard regressions."""
import json
import logging
import os
from types import SimpleNamespace

import pytest

from app.mcp import office_live
from app.mcp.office_com import WindowsOffice
from app.mcp.office_contracts import MAX_RESULT_BYTES, ReadArguments, canonical_json
from app.mcp.office_excel import OfficeConflict
from app.mcp.office_word import WordEdits
from app.mcp.office_word_document import signature
from tests.test_office_mcp_excel import service, read
from tests.test_office_mcp_live import tool


def populate(live, rows, columns):
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            live.backend.sheets["Sheet1"][(row, column)] = {
                "value": row * columns + column, "formula": "", "number_format": "General",
                "bold": False, "italic": False}


@pytest.mark.parametrize("columns", [10, 12])
def test_packed_pages_budget_normalized_defaults_and_retain_every_cell(monkeypatch, columns):
    # This check must reach the byte boundary regardless of machine speed.
    monkeypatch.setattr(office_live, "monotonic", lambda: 0, raising=False)
    live, authority, session = service()
    try:
        populate(live, 150, columns)
        cursor, seen, snapshots, pages = None, [], set(), 0
        while True:
            args = ReadArguments(session=session, target="Sheet1!used", cursor=cursor, max_items=1000)
            page = read(live, authority, session, target=args.target, cursor=cursor, max_items=args.max_items)
            result = tool("read").validate_result(args, page)
            assert len(canonical_json(result.model_dump(mode="json")).encode()) <= MAX_RESULT_BYTES == 16384
            snapshots.add(page["snapshot"])
            seen.extend(value for item in page["items"] for row in item["values"] for value in row)
            pages += 1
            cursor = page["cursor"]
            if cursor is None:
                break
        assert seen == [row * columns + column for row in range(1, 151) for column in range(1, columns + 1)]
        assert pages > 1 and len(snapshots) == 1 and live.backend.writes == 0
    finally:
        live.close()


def test_slow_excel_pages_yield_with_complete_cursor_coverage(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(office_live, "monotonic", lambda: clock[0], raising=False)
    live, authority, session = service()
    try:
        populate(live, 8, 10)
        original = live.backend.piece
        def slow_piece(*args):
            clock[0] += 0.75
            return original(*args)
        live.backend.piece = slow_piece
        cursor, seen, snapshots, pages = None, [], set(), 0
        while True:
            started = clock[0]
            args = ReadArguments(session=session, target="Sheet1!used", cursor=cursor, max_items=1000)
            page = read(live, authority, session, target=args.target, cursor=cursor, max_items=args.max_items)
            tool("read").validate_result(args, page)
            assert clock[0] - started <= 3.0  # Includes one continuation-guard cell.
            assert page["items"]  # Every yield makes progress.
            snapshots.add(page["snapshot"])
            seen.extend(value for item in page["items"] for row in item["values"] for value in row)
            pages += 1
            cursor = page["cursor"]
            if cursor is None:
                break
        assert seen == list(range(11, 91))
        assert pages > 1 and len(snapshots) == 1 and live.backend.writes == 0
    finally:
        live.close()


XML = ('<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" '
       'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
       '<pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document><w:body>'
       '<w:p><w:r><w:t>Synthetic body</w:t></w:r></w:p>'
       '</w:body></w:document></pkg:xmlData></pkg:part></pkg:package>')
PRIMED_XML = XML.replace('</pkg:package>', '<pkg:part pkg:name="/word/settings.xml">'
                        '<pkg:xmlData><w:settings/></pkg:xmlData></pkg:part></pkg:package>')


@pytest.mark.parametrize("unsupported", [False, True])
def test_native_guard_primes_preflight_and_still_detects_real_changes(unsupported):
    backend = WindowsOffice.__new__(WindowsOffice)
    backend.check_thread = lambda: None
    document = SimpleNamespace(Content=SimpleNamespace(WordOpenXML=XML))
    calls = []
    def preflight(doc):
        calls.append("preflight")
        if unsupported:
            raise OfficeConflict("Synthetic document is readable but cannot grant edit authority.")
        if len(calls) == 1:
            doc.Content.WordOpenXML = PRIMED_XML
    backend.word_xml_safe = preflight
    revision = backend.word_read_guard(document)
    assert calls == ["preflight"]
    assert revision == signature(XML if unsupported else PRIMED_XML)
    document.Content.WordOpenXML = document.Content.WordOpenXML.replace('Synthetic body', 'Changed body')
    assert backend.word_read_guard(document) != revision


def test_workflow_uses_the_same_primed_guard_as_native_reads():
    document = SimpleNamespace(Content=SimpleNamespace(WordOpenXML=XML))
    calls = []
    def guard(doc):
        calls.append("guard")
        doc.Content.WordOpenXML = PRIMED_XML
        return signature(doc.Content.WordOpenXML)
    edits = WordEdits(SimpleNamespace(backend=SimpleNamespace(word_read_guard=guard),
                                     documents={"document": ("word", document)}))
    workflow = edits.workflow({"document": {"document": "document"}})
    assert calls == ["guard"]
    assert workflow.revision == signature(PRIMED_XML)


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio timeout")
def test_read_timeout_persists_content_free_failure_and_releases_worker(tmp_path):
    from app.capabilities.contracts import CapabilityExecutionError, CapabilityErrorCode
    from app.vault.logging import ProfileLogHandler
    from tests.test_office_mcp_connection import connection, attach, invoke
    path = tmp_path / "events.json"
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _: path, register=lambda **_: None))
    logger = logging.getLogger("app.mcp.office_read_diagnostics")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    bridge = connection("hang_read", call_timeout=0.2)
    try:
        bridge.connect()
        attach(bridge)
        with pytest.raises(CapabilityExecutionError) as error:
            invoke(bridge, "office.read", {"session": "s1", "target": "PRIVATE-WORKSHEET!used"}, "read1")
        assert error.value.code in {CapabilityErrorCode.TIMED_OUT, CapabilityErrorCode.INVALID_OUTPUT}
        events = json.loads(path.read_text())
        assert events[-1]["stage"] == "bridge" and events[-1]["reason"] in {"timeout", "transport"}
        assert events[-1]["timeout_ms"] == 200 and events[-1]["target_kind"] == "excel_used"
        assert "PRIVATE" not in path.read_text() and "s1" not in path.read_text()
    finally:
        bridge.close()
        logger.removeHandler(handler)
        logger.setLevel(level)
        handler.close()
    assert not bridge.diagnostics["worker_alive"]
