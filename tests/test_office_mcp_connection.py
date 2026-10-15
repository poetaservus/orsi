"""Essential real SDK/stdio checks; all document contents are synthetic fixtures."""
import os
from pathlib import Path
import sys
from threading import Timer
from time import monotonic

import pytest

from app.capabilities.contracts import CapabilityExecutionError, CapabilityErrorCode
from app.mcp.office_contracts import OFFICE_TOOLS
from app.runtime.cancellation import CancellationSource, CancellationToken, TaskCancelled
from app.mcp.office_connection import OfficeConnection
from app.mcp.stdio_transport import OwnedStdioTransport


ROOT = Path(__file__).resolve().parents[1]


def connection(mode="normal", **kwargs):
    return OfficeConnection(ROOT, backend=lambda: "cloud", applications=("excel",),
        _transport_factory=lambda: OwnedStdioTransport(
            [sys.executable, "-m", "tests.fixtures.office_mcp_server", mode], root=ROOT), **kwargs)


def invoke(bridge, name, arguments, operation, cancellation=None):
    tool = next(tool for tool in OFFICE_TOOLS if tool.name == name)
    return bridge.call(tool, tool.arguments.model_validate(arguments), expected=bridge.exposure,
                       operation=operation, cancellation=cancellation or CancellationToken())


def attach(bridge):
    return invoke(bridge, "office.attach", {"application": "excel", "document": "d1"}, "attach1")


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
def test_real_sdk_handshake_caches_reviewed_tools_and_closes_worker():
    bridge = connection()
    try:
        assert bridge.connect().eligible
        assert bridge.diagnostics["tool_list_requests"] == 1
    finally:
        bridge.close()
    assert not bridge.diagnostics["worker_alive"]


def test_local_mode_rejects_start_before_creating_a_transport():
    def forbidden():
        pytest.fail("Local mode must not launch an Office bridge")
    bridge = OfficeConnection(ROOT, backend=lambda: "local", _transport_factory=forbidden)
    with pytest.raises(CapabilityExecutionError):
        bridge.connect()
    bridge.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
def test_persistent_calls_use_one_discovery_and_forward_structured_content_once():
    bridge = connection()
    try:
        bridge.connect()
        pid = bridge.diagnostics["pid"]
        assert attach(bridge)["session"] == "s1"
        first = invoke(bridge, "office.read", {"session": "s1"}, "read1")
        assert first["items"][0]["values"] == [[1]]
        assert "Duplicate content" not in str(first)
        changed = invoke(bridge, "office.excel_edit", {"session": "s1", "snapshot": "snap1",
            "changes": [{"sheet": "Sheet1", "range": "A1", "values": [[42]]}]}, "edit1")
        assert changed["operation"] == "edit1"
        second = invoke(bridge, "office.read", {"session": "s1"}, "read2")
        assert second["items"][0]["values"] == [[42]]
        assert bridge.diagnostics["pid"] == pid and bridge.diagnostics["tool_list_requests"] == 1
        with pytest.raises(CapabilityExecutionError) as caught:
            invoke(bridge, "office.read", {"session": "s1"}, "read2")
        assert caught.value.code == CapabilityErrorCode.CALL_REPLAYED
    finally:
        bridge.close()
    assert bridge._transport.process.poll() is not None


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
@pytest.mark.parametrize("mode", ["bad_schema", "extra_tool", "oversized_frame"])
def test_unreviewed_or_oversized_servers_never_become_ready_and_release_process(mode):
    bridge = connection(mode)
    try:
        with pytest.raises(CapabilityExecutionError):
            bridge.connect()
        assert not bridge.exposure.eligible
        assert not bridge.diagnostics["worker_alive"]
        assert bridge._transport.process.poll() is not None
    finally:
        bridge.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
def test_startup_timeout_releases_owned_process():
    bridge = connection("hang_start", startup_timeout=0.2)
    started = monotonic()
    try:
        with pytest.raises(CapabilityExecutionError) as caught:
            bridge.connect()
        assert caught.value.code == CapabilityErrorCode.TIMED_OUT
        assert monotonic() - started < 7
        assert bridge._transport.process.poll() is not None
        assert not bridge.diagnostics["worker_alive"]
    finally:
        bridge.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
@pytest.mark.parametrize("mode", ["hang_call", "crash_call", "bad_result"])
def test_read_failures_are_bounded_redacted_and_disconnect(mode, caplog):
    bridge = connection(mode, call_timeout=0.2)
    try:
        bridge.connect()
        with pytest.raises(CapabilityExecutionError) as caught:
            invoke(bridge, "office.documents", {}, "read1")
        assert caught.value.code in {CapabilityErrorCode.INVALID_OUTPUT, CapabilityErrorCode.TIMED_OUT}
        assert "SECRET-FIXTURE" not in str(caught.value) + caplog.text
        bridge.disconnect()
        assert not bridge.exposure.ready and not bridge.diagnostics["worker_alive"]
    finally:
        bridge.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
def test_sent_write_cancellation_is_unknown_and_disconnect_invalidates_old_sessions():
    bridge = connection("hang_write", call_timeout=2)
    source = CancellationSource()
    timer = Timer(0.1, source.cancel)
    try:
        bridge.connect()
        attach(bridge)
        old = bridge.exposure
        timer.start()
        with pytest.raises(CapabilityExecutionError) as caught:
            invoke(bridge, "office.excel_edit", {"session": "s1", "snapshot": "snap1",
                "changes": [{"sheet": "Sheet1", "range": "A1", "bold": True}]}, "edit1", source.token)
        assert caught.value.code == CapabilityErrorCode.OUTCOME_UNKNOWN
        assert not bridge.exposure.ready and bridge.exposure.generation > old.generation
        assert not bridge.diagnostics["worker_alive"]
        bridge.connect()
        with pytest.raises(CapabilityExecutionError) as caught:
            invoke(bridge, "office.read", {"session": "s1"}, "read1")
        assert caught.value.code == CapabilityErrorCode.PERMISSION_DENIED
    finally:
        timer.cancel()
        bridge.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned stdio bridge")
def test_presend_cancellation_does_not_send_a_tool_call():
    bridge = connection()
    source = CancellationSource()
    try:
        bridge.connect()
        source.cancel()
        with pytest.raises(TaskCancelled):
            invoke(bridge, "office.documents", {}, "read1", source.token)
        assert bridge.diagnostics["tool_calls"] == 0
    finally:
        bridge.close()
