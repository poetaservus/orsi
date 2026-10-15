"""Opt-in live Office gates. Only newly created synthetic documents are touched."""
import gc
import os
from time import monotonic, sleep

import pytest

from app.mcp.office_connection import OfficeConnection
from app.mcp.office_discovery import OFFICE_REGISTRATIONS
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_capabilities import runtime_for
from tests.test_office_mcp_live import execute


pytestmark = pytest.mark.skipif(os.environ.get("ORSI_TEST_LIVE_OFFICE") != "1",
                                reason="Live Office gate requires explicit opt-in and an interactive desktop")


@pytest.mark.parametrize("kind", ["excel", "word", "powerpoint"])
def test_live_unsaved_documents_and_multiple_instances_keep_exact_session(kind, tmp_path):
    import pythoncom
    import win32com.client.dynamic
    import win32com.client
    import win32process
    import psutil

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    applications, documents = [], []
    prior = {p.pid for p in psutil.process_iter(["name"]) if
             (p.info["name"] or "").lower() == OFFICE_REGISTRATIONS[kind][1].lower()}
    bridge = OfficeConnection(ROOT, backend=lambda: "cloud", startup_timeout=20)
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        for index in range(2 if kind in ("excel", "word") else 1):
            stage = "application activation"
            try:
                application = win32com.client.DispatchEx(OFFICE_REGISTRATIONS[kind][0])
                applications.append((application, False, None))
                stage = "visible window"
                application.Visible = True
                collection = getattr(application, {"excel": "Workbooks", "word": "Documents",
                                                    "powerpoint": "Presentations"}[kind])
                stage = "synthetic document creation"
                document = collection.Add()
                documents.append(document)
                # Window.Hwnd is document-bound in Word; PowerPoint can report HWND as a method.
                stage = "window identity"
                if kind == "powerpoint":
                    new = {p.pid for p in psutil.process_iter(["name"]) if
                           (p.info["name"] or "").lower() == "powerpnt.exe"} - prior
                    pid = next(iter(new)) if len(new) == 1 else None
                    applications[-1] = (application, pid is not None, pid)
                else:
                    handle = document.ActiveWindow.Hwnd if kind == "word" else application.Hwnd
                    pid = win32process.GetWindowThreadProcessId(int(handle))[1]
                    applications[-1] = (application, pid not in prior, pid)
                stage = "synthetic content setup"
                value = "ORSI synthetic " + kind + " " + str(index)
                if kind in ("word", "powerpoint"):
                    value += " \U0001f642"
                if kind == "excel":
                    document.Worksheets.Item(1).Range("A1").Value2 = value
                    document.Worksheets.Item(1).Range("A2").Formula = "=2+3"
                elif kind == "word":
                    document.Content.Text = value
                else:
                    slide = document.Slides.Add(1, 12)
                    shape = slide.Shapes.AddTextbox(1, 40, 40, 300, 80)
                    shape.TextFrame.TextRange.Text = value
            except pythoncom.com_error as error:
                pytest.skip("Installed " + kind + " is unavailable during " + stage +
                            " (HRESULT " + str(error.hresult) + ")")
        if kind == "powerpoint":
            # PowerPoint is normally a singleton; qualify two independent
            # presentations in that same application instead of claiming two instances.
            document = application.Presentations.Add()
            documents.append(document)
            applications.append((application, False, pid))
            slide = document.Slides.Add(1, 12)
            shape = slide.Shapes.AddTextbox(1, 40, 40, 300, 80)
            shape.TextFrame.TextRange.Text = "ORSI synthetic powerpoint 1 \U0001f642"
        bridge.connect()
        deadline = monotonic() + 8
        while True:
            values = bridge.list_documents()
            names = {str(document.Name) for document in documents}
            matching = [v for v in values if v["application"] == kind and v["title"] in names]
            if len(matching) == len(documents):
                break
            if monotonic() >= deadline:
                break
            pythoncom.PumpWaitingMessages()
            sleep(0.15)
        # Excel instances can share unsaved Book1 names; IDs must still be distinct.
        assert len(matching) >= len(documents)
        assert len({d["document"] for d in matching}) == len(matching)
        received = []
        for index, metadata in enumerate(matching[:len(documents)]):
            assert not metadata["has_path"] and metadata["dirty"]
            bridge.select_document(metadata["document"])
            attached = execute(runtime, "attach", {"application": kind, "document": metadata["document"]}, "attach" + str(index))
            assert attached.success
            arguments = {"session": attached.output["session"], "target": {
                "excel": "Sheet1!A1:A2", "word": "document", "powerpoint": "slide:1"}[kind]}
            read = execute(runtime, "read", arguments, "read" + str(index))
            assert read.success
            text = "".join(item.get("text") or "" for item in read.output["items"])
            if kind == "excel":
                text = read.output["items"][0]["values"][0][0]
                assert read.output["items"][1]["values"] == [[5.0]]
                assert read.output["items"][1]["formulas"] == [["=2+3"]]
            received.append(text.strip())
            if kind in ("word", "powerpoint"):
                cursor, chunks, page = None, [], 0
                while True:
                    paged = execute(runtime, "read", {**arguments, "max_chars": 1, "cursor": cursor},
                                    "unicode" + str(index) + "_" + str(page))
                    assert paged.success
                    chunks.extend(item.get("text") or "" for item in paged.output["items"])
                    cursor, page = paged.output["cursor"], page + 1
                    if cursor is None:
                        break
                assert "".join(chunks).strip() == text.strip()
            # The other application/document is foreground; this session stays bound.
            if len(documents) > 1:
                if kind == "powerpoint":
                    documents[-1].Windows.Item(1).Activate()
                else:
                    documents[-1].Activate()
                again = execute(runtime, "read", arguments, "again" + str(index))
                assert again.success and [item.get("text") or item.get("values") for item in again.output["items"]] == [
                    item.get("text") or item.get("values") for item in read.output["items"]]
        expected = {"ORSI synthetic " + kind + " " + str(i) +
                    (" \U0001f642" if kind in ("word", "powerpoint") else "") for i in range(len(documents))}
        assert set(received) == expected
        assert bridge.discovery.runs == 1
        runtime.shutdown()
        # Disconnect releases only the bridge, preserving the user's open unsaved work.
        assert all(str(document.Name) for document in documents)
    finally:
        runtime.shutdown()
        for index in reversed(range(len(documents))):
            document = documents[index]
            try:
                if applications[index][1]:
                    # Mark only the test-created document clean, then Quit its
                    # provably new application once. Avoid calls to closed proxies.
                    document.Saved = True
                elif kind == "powerpoint":
                    document.Saved = True
                    document.Close()
                else:
                    document.Close(False)
            except pythoncom.com_error:
                pass
        documents.clear()
        owned_pids = [pid for _, owned, pid in applications if owned]
        for application, owned, pid in reversed(applications):
            if owned and psutil.pid_exists(pid):
                try:
                    application.Quit()
                except pythoncom.com_error:
                    pass
        applications.clear()
        # Drop every local proxy before balancing COM initialization. Pytest can
        # retain failure frames; do not uninitialize an apartment with retained proxies.
        document = collection = application = handle = shape = slide = None
        gc.collect()
        for pid in owned_pids:
            try:
                psutil.Process(pid).wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
    assert not bridge.diagnostics["worker_alive"]
