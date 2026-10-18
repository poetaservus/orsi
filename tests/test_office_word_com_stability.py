"""Essential outcome, STA and pagination regressions; native documents are disposable."""
import asyncio
import gc
import json
import logging
import os
from threading import get_ident
from types import SimpleNamespace
from xml.etree.ElementTree import Element

import pytest

from app.mcp.office_contracts import WordComposeArguments
from app.mcp.office_excel import OfficeConflict, OfficeUnknown
from app.mcp.office_live import OfficeSTA
from app.mcp.office_word import WordNotApplied
from app.mcp.office_word_document import paragraph, effective_format, W, finalize_layout
from app.mcp.office_write_diagnostics import record_write_event, safe_write_event, native_step
from tests.test_office_mcp_word import service, read, patch, mutate


@pytest.mark.parametrize("style", ["Normal", "Title", "Heading 1", "Heading 2"])
@pytest.mark.parametrize("page_break", [False, True])
def test_generated_pagination_explicitly_overrides_source_style(style, page_break):
    plan = WordComposeArguments(session="s", snapshot="r", blocks=[{"text": "Synthetic", "style": style}])
    fmt = effective_format(plan, plan.blocks[0])
    props = paragraph(Element(W + "body"), "Synthetic", "style", fmt, page_break=page_break).find(W + "pPr")
    assert props.find(W + "keepNext").get(W + "val") == str(int(fmt["keep_with_next"]))
    assert props.find(W + "keepLines").get(W + "val") == "0"
    assert props.find(W + "pageBreakBefore").get(W + "val") == str(int(page_break))


def test_finalization_orders_pagination_then_fields_then_reflow():
    calls = []
    part = SimpleNamespace(Exists=True, Range=SimpleNamespace(Fields=SimpleNamespace(Update=lambda: calls.append("field"))))
    section = SimpleNamespace(Headers=SimpleNamespace(Item=lambda _:part), Footers=SimpleNamespace(Item=lambda _:part))
    document = SimpleNamespace(Repaginate=lambda:calls.append("paginate"), Sections=SimpleNamespace(Count=1, Item=lambda _:section))
    finalize_layout(document)
    assert calls == ["paginate", "field", "field", "paginate"]


@pytest.mark.parametrize("value,disabled", [("1",True), ("true",True), ("0",False), ("false",False)])
def test_disabled_column_balance_is_refused_before_com_dispatch(value, disabled):
    from app.mcp.office_word_document import compile_packet, column_balance_disabled
    from xml.etree.ElementTree import SubElement, tostring
    root = Element(W + "settings")
    SubElement(SubElement(root,W + "compat"), W + "noColumnBalance", {W + "val":value})
    assert column_balance_disabled(root) == disabled
    if disabled:
        plan = WordComposeArguments(session="s",snapshot="r",sections=[{"columns":2,"blocks":[{"text":"Synthetic"}]}])
        # No COM object is needed to reject this incompatible source setting.
        with pytest.raises(OfficeConflict, match="disables column balancing"):
            compile_packet(None,plan,{"xml":tostring(root,encoding="unicode")})


def test_final_column_terminator_is_bounded_and_does_not_accumulate():
    from app.mcp.office_word_document import section_specs
    for columns, expected in ((1,1),(2,2)):
        plan = WordComposeArguments(session="s",snapshot="r",sections=[{"columns":columns,"blocks":[{"text":"Synthetic"}]}])
        first, second = section_specs(plan), section_specs(plan)
        assert first == second and len(first) == expected
        if columns == 2:
            assert first[-1] == {"columns":1, "column_spacing_mm":0, "start":"continuous", "terminal":True}


@pytest.mark.parametrize("hresult", [-2147418111, -2147417846])
def test_rejected_write_is_read_back_before_fresh_approval_can_retry(hresult):
    live, authority, session = service()
    view = read(live, authority, session)
    original = live.backend.write_word
    attempted = []
    def reject(*args):
        attempted.append(1)
        error = RuntimeError("PRIVATE exception text")
        error.hresult = hresult
        raise error
    live.backend.write_word = reject
    with pytest.raises(WordNotApplied) as caught:
        mutate(live, authority, "word_edit", patch(session, view))
    assert caught.value.diagnostic["outcome"] == "not_applied"
    assert caught.value.diagnostic["category"] in {"busy", "rejected"}
    assert not live.word.blocked and live.backend.writes == 0 and len(attempted) == 1
    # Consumed guards and snapshots cannot be replayed, even for unchanged state.
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", patch(session, view))
    live.backend.write_word = original
    result = mutate(live, authority, "word_edit", patch(session, read(live, authority, session)))
    assert result["outcome"] == "applied" and live.backend.writes == 1


@pytest.mark.parametrize("action", ["replace_text", "insert_after", "apply_style", "edit_table"])
def test_exception_after_complete_write_returns_verified_receipt_without_replay(action):
    from tests.test_office_word_actions import arguments, page
    live, authority, session = service()
    if action == "replace_text":
        args = patch(session, read(live, authority, session))
        method = "write_word"
    else:
        args = arguments(session, page(live, authority, session, action), action)
        method = {"insert_after":"write_word", "apply_style":"write_word_style", "edit_table":"write_word_table"}[action]
    original = getattr(live.backend, method)
    def write_then_fail(*args):
        original(*args)
        raise RuntimeError("PRIVATE post-write failure")
    setattr(live.backend, method, write_then_fail)
    result = mutate(live, authority, "word_edit", args)
    assert result["outcome"] == "applied" and result["recovery"] in live.word.recoveries
    assert live.backend.writes == 1 and not live.word.blocked
    assert live.word.last_diagnostic["outcome"] == "applied"
    assert not live.word.last_diagnostic["retry_safe"]
    with pytest.raises(OfficeConflict):
        mutate(live, authority, "word_edit", args)
    assert live.backend.writes == 1


def test_partial_write_and_failed_outcome_read_remain_blocked():
    live, authority, session = service()
    view = read(live, authority, session)
    original = live.backend.capture_word
    def partial(*args):
        live.backend.docs[0]["value"] = "Partial"
        live.backend.writes += 1
        live.backend.capture_word = lambda *args: (_ for _ in ()).throw(RuntimeError("Busy during verification"))
        raise RuntimeError("PRIVATE mutation failure")
    live.backend.write_word = partial
    with pytest.raises(OfficeUnknown):
        mutate(live, authority, "word_edit", patch(session, view))
    assert live.word.blocked and live.backend.writes == 1
    live.backend.capture_word = original
    assert live.word.last_diagnostic["outcome"] == "unknown"
    assert not live.word.last_diagnostic["retry_safe"]


def test_profile_persists_only_allowlisted_operation_evidence(tmp_path):
    from app.vault.logging import ProfileLogHandler
    path = tmp_path / "events.json"
    handler = ProfileLogHandler(SimpleNamespace(storage_path=lambda _:path, register=lambda **_:None))
    logger = logging.getLogger("app.mcp.office_write_diagnostics")
    prior = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        record_write_event({"tool":"office.word_compose", "stage":"insert_xml", "category":"busy",
            "outcome":"unknown", "hresult":-2147417846, "duration_ms":102,
            "path":"PRIVATE", "exception":"PRIVATE", "arguments":{"text":"PRIVATE"},
            "shape":{"paragraphs":2, "images":4, "text":"PRIVATE"}})
        event = json.loads(path.read_text())[0]
        assert event["duration_ms"] == 102 and event["shape"]["images"] == 4
        assert "PRIVATE" not in path.read_text() and not event["retry_safe"]
        assert safe_write_event({"stage":[], "hresult":"PRIVATE"})["stage"] == "confirmation"
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior)
        handler.close()


@pytest.mark.parametrize("mode,outcome", [("busy","not_applied"),("after_apply","applied")])
def test_structured_outcomes_cross_actual_sta_sdk_and_executor(mode, outcome, tmp_path):
    from app.capabilities.contracts import CapabilityErrorCode
    from tests.test_office_mcp_word import connection
    from tests.test_office_mcp_capabilities import runtime_for
    from tests.test_office_mcp_live import execute
    bridge = connection(mode)
    runtime = runtime_for(bridge,tmp_path,policy=bridge.resource_policy)
    try:
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        session = execute(runtime,"attach",{"application":"word","document":document["document"]},"attach").output["session"]
        view = execute(runtime,"read",{"session":session},"read").output
        result = execute(runtime,"word_edit",patch(session,view),"edit")
        assert result.success == (outcome == "applied")
        if outcome == "not_applied":
            assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
        else:
            assert result.output["outcome"] == "applied"
        event = bridge.diagnostics["write_outcome"]
        assert event["outcome"] == outcome and event["action"] == "replace_text"
        assert bridge.exposure.ready and not runtime.executor.journal.review_required
        assert "SECRET" not in json.dumps(bridge.diagnostics)
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


def test_native_step_keeps_innermost_stage_and_hresult():
    error = RuntimeError("PRIVATE")
    error.hresult = -2147417846
    with pytest.raises(RuntimeError) as caught, native_step("word_document_write"), native_step("insert_xml"):
        raise error
    assert caught.value.orsi_write_stage == "insert_xml"
    assert caught.value.orsi_write_step_ms >= 0


@pytest.mark.parametrize("sent,mutated", [(False,False), (True,False), (True,True)])
def test_confirmation_timeout_does_not_infer_or_repeat_a_mutation(sent, mutated):
    from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityExecutionError as Error
    from app.runtime.cancellation import CancellationToken
    from tests.test_office_word_completion import connection, COMPOSE, ARGS
    bridge = connection(call_timeout=.05)
    bridge._enabled = bridge._ready = True
    bridge._generation = 1
    bridge._sessions["s1"] = "word"
    writes = []
    def dispatch(request):
        request.sent = sent
        if mutated:
            writes.append("side effect")
    bridge._queue = SimpleNamespace(put_nowait=dispatch)
    bridge._loop = SimpleNamespace(call_soon_threadsafe=lambda callback, request:callback(request))
    bridge.disconnect = lambda:None
    with pytest.raises(Error) as caught:
        bridge.call(COMPOSE, COMPOSE.arguments.model_validate(ARGS), expected=bridge.exposure,
                    operation="timeout", cancellation=CancellationToken())
    assert caught.value.code == (Code.OUTCOME_UNKNOWN if sent else Code.TIMED_OUT)
    event = bridge.diagnostics["write_outcome"]
    assert event["category"] == "timeout"
    assert event["outcome"] == ("unknown" if sent else "not_applied")
    assert len(writes) == int(mutated)


def test_repeated_formatting_is_verified_unchanged_without_another_write():
    from tests.test_office_word_actions import arguments, page
    live, authority, session = service()
    mutate(live, authority, "word_edit", arguments(session, page(live, authority, session, "apply_style"), "apply_style"))
    result = mutate(live, authority, "word_edit", arguments(session, page(live, authority, session, "apply_style"), "apply_style"))
    assert result["outcome"] == "unchanged" and live.backend.writes == 1


def test_verified_save_receipt_survives_failed_post_save_authority_refresh(tmp_path):
    from tests.test_office_word_completion import connection
    from tests.test_office_mcp_live import tool
    from app.mcp.office_connection import _Request
    bridge = connection()
    bridge.live = True
    bridge._enabled = bridge._ready = True
    bridge._generation = 1
    bridge._sessions["s1"] = "word"
    calls = []
    async def run():
        bridge._queue = asyncio.Queue()
        async def check(client):
            pass
        async def control(client, action, data):
            if action == "binding":
                raise RuntimeError("PRIVATE post-save connection loss")
            return {}
        async def call(*args, **kwargs):
            calls.append(1)
            return SimpleNamespace(is_error=False, meta={}, result_type="complete",
                structured_content={"session":"s1", "operation":"save1", "saved":True})
        bridge._check_server = check
        bridge._control_request = control
        request = _Request(tool("save"), {"session":"s1", "path":str(tmp_path/"saved.docx")}, bridge.exposure, "save1")
        await bridge._queue.put(request)
        await bridge._connected(SimpleNamespace(call_tool=call))
        assert request.future.result()["saved"] is True
    asyncio.run(run())
    assert calls == [1] and not bridge.exposure.ready
    assert bridge.diagnostics["save_binding_unavailable"]
    assert bridge.diagnostics["write_outcome"]["outcome"] == "saved"


@pytest.mark.parametrize("failure_point", ["after_insert", "readback"])
def test_complete_composition_with_images_is_verified_without_reinserting(monkeypatch, failure_point):
    from app.mcp.office_word import WordEdits
    import app.mcp.office_word_document as native
    plan = WordComposeArguments(session="s", snapshot="snap", blocks=[{"text":"Synthetic"},
        {"kind":"image", "asset":"picture", "width_mm":50, "alt_text":"Synthetic picture"}])
    before = {"kind":"document", "fingerprint":"before"}
    after = {"kind":"document", "fingerprint":"after"}
    document = SimpleNamespace(Content=SimpleNamespace(End=10), state=before)
    inserts, reads = [], []
    def capture(descriptor):
        reads.append(1)
        if failure_point == "readback" and len(reads) == 2:
            raise RuntimeError("Transient capture failure")
        return document.state
    backend = SimpleNamespace(word_writable=lambda _:None, capture_word=capture)
    edits = WordEdits(SimpleNamespace(backend=backend, documents={"d":("word",document)}))
    binding = {"identity":"identity", "document":{"document":"d"}}
    expected = {"packet":"private packet", "plan":plan.model_dump(), "media":{}}
    edits.guards["g"] = ("office.word_compose", plan.model_dump(mode="json"), "identity",
        ("word_document",document,0,10), before, expected, None, 0, "compose")
    def write(*args):
        inserts.append(1)
        document.state = after
        if failure_point == "after_insert":
            raise RuntimeError("Transient return failure")
    monkeypatch.setattr(native, "write_document", write)
    monkeypatch.setattr(native, "verify_document", lambda *args:None)
    result = edits.execute("office.word_compose", plan, binding, {"guard":"g"}, "operation")
    assert result["outcome"] == "applied" and inserts == [1] and not edits.blocked
    assert edits.recoveries[result["recovery"]][3:5] == (before,after)


def test_sta_releases_exception_local_proxies_on_owner_and_serializes_calls():
    threads, released = [], []
    class Proxy:
        def __del__(self):
            released.append(get_ident())
    class Service:
        def __init__(self):
            threads.append(get_ident())
        def fail(self):
            proxy = Proxy()
            error = RuntimeError("PRIVATE native message")
            error.hresult = -2147417846
            raise error
        def call_id(self):
            threads.append(get_ident())
            return len(threads)
        def close(self):
            threads.append(get_ident())
    async def run():
        sta = OfficeSTA(Service)
        try:
            with pytest.raises(RuntimeError) as caught:
                await sta.invoke("fail")
            assert str(caught.value) == "Office execution failed."
            assert caught.value.hresult == -2147417846 and caught.value.__context__ is None
            assert await asyncio.gather(*(sta.invoke("call_id") for _ in range(4))) == [2,3,4,5]
        finally:
            await sta.close()
    asyncio.run(run())
    assert len(set(threads)) == 1 and threads[0] != get_ident()
    assert released == [threads[0]]


@pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1", reason="Disposable native Word gate")
def test_native_inherited_pagination_columns_captions_save_reopen(tmp_path):
    import pythoncom
    import psutil
    import win32com.client
    import win32process
    from app.mcp.office_com import WindowsOffice
    from app.mcp.office_word_document import (capture_document, compile_packet, write_document,
        verify_document, restore_document, same_document)
    from tests.test_office_word_pictures_columns import section_plan, image_bytes
    from app.mcp.office_word_assets import inspect_image
    pythoncom.CoInitializeEx(2)
    application = document = reopened = backend = owned = None
    try:
        prior = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "winword.exe"}
        application = win32com.client.DispatchEx("Word.Application")
        application.Visible = True
        document = application.Documents.Add()
        pid = win32process.GetWindowThreadProcessId(int(document.ActiveWindow.Hwnd))[1]
        assert pid not in prior
        owned = psutil.Process(pid)
        backend = WindowsOffice()
        normal = document.Styles.Item(-1).ParagraphFormat
        normal.KeepWithNext = normal.KeepTogether = normal.PageBreakBefore = True
        normal = None
        # Equal body paragraphs must use both final-page columns instead of
        # inheriting page breaks/keep chains and leaving seven mostly blank pages.
        flow = WordComposeArguments(session="s", snapshot="r", page_numbers="none", sections=[
            {"columns":2, "blocks":[{"text":"Synthetic flowing paragraph. " * 15} for _ in range(8)]}])
        source = capture_document(backend, document)
        write_document(backend, document, compile_packet(document, flow, source), flow)
        verify_document(document, flow)
        assert int(document.Range(0,0).Information(4)) == 1
        ends = []
        for number in (4,8):
            end = int(document.Paragraphs.Item(number).Range.End) - 2
            region = document.Range(end,end)
            ends.append((float(region.Information(5)),float(region.Information(6))))
        region = None
        assert ends[0][0] < float(document.PageSetup.PageWidth)/2 < ends[1][0]
        assert abs(ends[0][1] - ends[1][1]) < 20
        (tmp_path / "balance-evidence.json").write_text(json.dumps({"pages":1,
            "column_end_points":ends, "bottom_difference_points":abs(ends[0][1]-ends[1][1])}))
        flow_path = tmp_path / "balanced-flow.docx"
        backend.save_word(document, {"path":str(flow_path), "save_as":True})
        # Opening an already-open path in the same Word instance aliases the
        # original document. Reopen a byte-identical disposable copy instead.
        reopen_path = tmp_path / "balanced-flow-reopen.docx"
        reopen_path.write_bytes(flow_path.read_bytes())
        reopened = application.Documents.Open(str(reopen_path), ReadOnly=True, AddToRecentFiles=False)
        reopened.Repaginate()
        verify_document(reopened, flow)
        assert int(reopened.Sections.Count) == 2 and int(reopened.Range(0,0).Information(4)) == 1
        reopened.Close(False)
        reopened = None
        restore_document(backend, document, source)
        assert same_document(capture_document(backend,document), source)
        # 1 -> 2 -> 1 continuous sections, native images and editable captions.
        value = section_plan()
        value["sections"][-1]["start"] = "continuous"
        plan = WordComposeArguments.model_validate(value)
        media = {key:(image_bytes(color=color), inspect_image(image_bytes(color=color)))
                 for key,color in (("first","red"),("second","blue"))}
        original = capture_document(backend, document)
        packet = compile_packet(document, plan, original, media)
        for _ in range(2):
            write_document(backend, document, packet, plan)
            verify_document(document, plan)
            assert int(document.InlineShapes.Count) == 2 and int(document.Sections.Count) == 3
            assert [int(document.Sections.Item(i).PageSetup.TextColumns.Count) for i in (1,2,3)] == [1,2,1]
            for number in range(1, int(document.InlineShapes.Count)+1):
                picture = document.InlineShapes.Item(number)
                caption = document.Range(int(picture.Range.End)+1, int(picture.Range.End)+2).Paragraphs.Item(1)
                assert bool(caption.KeepWithNext) and not bool(caption.PageBreakBefore)
                picture = caption = None
        path = tmp_path / "disposable.docx"
        background = bool(application.Options.BackgroundSave)
        backend.save_word(document, {"path":str(path), "save_as":True})
        assert bool(application.Options.BackgroundSave) == background
        document.Close(False)
        document = None
        reopened = application.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
        reopened.Repaginate()
        verify_document(reopened, plan)
        assert int(reopened.InlineShapes.Count) == 2
    finally:
        for doc in (reopened, document):
            if doc is not None:
                try:
                    doc.Close(False)
                except pythoncom.com_error:
                    pass
        doc = reopened = document = None
        if application is not None and owned is not None:
            application.Quit()
        application = None
        gc.collect()
        if backend is not None:
            backend.close()
        if owned is not None:
            owned.wait(10)
        pythoncom.CoUninitialize()
