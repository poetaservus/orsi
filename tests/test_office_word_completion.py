"""Report confirmation uses one consistent budget without replay or false success."""
from concurrent.futures import Future, TimeoutError as FutureTimeout
import os
from threading import Event, Thread, Timer
from time import monotonic
from types import SimpleNamespace

import pytest

from app.capabilities.contracts import CapabilityErrorCode as Code, CapabilityExecutionError as Error
from app.mcp.office_capabilities import OfficeCapability
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_contracts import OFFICE_TOOLS
from app.mcp.stdio_transport import OwnedStdioTransport
from app.runtime.cancellation import CancellationSource, CancellationToken
from tests.test_office_mcp_connection import ROOT, invoke
import sys


COMPOSE = next(t for t in OFFICE_TOOLS if t.name == "office.word_compose")
ARGS = {"session": "s1", "snapshot": "snap1", "blocks": [{"kind": "paragraph", "text": "Synthetic report"}]}


def connection(mode="slow_word", **kwargs):
    return OfficeConnection(ROOT, backend=lambda: "cloud", applications=("word",),
        _transport_factory=lambda: OwnedStdioTransport(
            [sys.executable, "-m", "tests.fixtures.office_mcp_server", mode], root=ROOT), **kwargs)


def test_word_composition_budgets_cover_controls_verification_and_shutdown_only_for_that_tool():
    bridge = connection()
    try:
        assert bridge.call_timeout == 10
        assert bridge.tool_timeout(COMPOSE) == 60
        tool = OfficeCapability(COMPOSE, bridge, None, None, None)
        assert tool.timeout_seconds == 90
        for contract in OFFICE_TOOLS:
            if contract.name not in {COMPOSE.name, "office.excel_edit"}:
                assert bridge.tool_timeout(contract) == 10
                assert OfficeCapability(contract, bridge, None, None, None).timeout_seconds == 40
        excel = next(t for t in OFFICE_TOOLS if t.name == "office.excel_edit")
        assert bridge.tool_timeout(excel) == 240
        assert OfficeCapability(excel, bridge, None, None, None).timeout_seconds == 500
    finally:
        bridge.close()


def test_explicit_short_deadlines_remain_authoritative_for_hung_operation_checks():
    bridge = connection(call_timeout=.2)
    try:
        assert bridge.tool_timeout(COMPOSE) == .2
        assert OfficeCapability(COMPOSE, bridge, None, None, None).timeout_seconds == 40
    finally:
        bridge.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP transport")
def test_real_sdk_waits_for_a_valid_report_receipt_beyond_the_old_ten_second_deadline():
    bridge = connection()
    try:
        bridge.connect()
        invoke(bridge, "office.attach", {"application": "word", "document": "d1"}, "attach1")
        started = monotonic()
        receipt = invoke(bridge, COMPOSE.name, ARGS, "compose1")
        assert 10 < monotonic() - started < bridge.tool_timeout(COMPOSE)
        assert receipt["outcome"] == "applied" and receipt["operation"] == "compose1"
        assert bridge.diagnostics["tool_calls"] == 2  # attach + exactly one write
        assert bridge.exposure.ready
    finally:
        bridge.close()
    assert not bridge.diagnostics["worker_alive"] and bridge.diagnostics["temporary_released"]


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP transport")
@pytest.mark.parametrize("cancel", [False, True])
def test_unconfirmed_or_cancelled_report_still_requires_review_without_replay(cancel):
    bridge = connection("hang_word", call_timeout=.3)
    source = CancellationSource()
    timer = Timer(.1, source.cancel) if cancel else None
    try:
        bridge.connect()
        invoke(bridge, "office.attach", {"application": "word", "document": "d1"}, "attach1")
        if timer:
            timer.start()
        with pytest.raises(Error) as caught:
            invoke(bridge, COMPOSE.name, ARGS, "compose1", source.token)
        assert caught.value.code == Code.OUTCOME_UNKNOWN
        assert bridge.diagnostics["tool_calls"] == 2
        assert not bridge.exposure.ready and not bridge.diagnostics["worker_alive"]
        if cancel:
            assert bridge.diagnostics["confirmation_stop"] == "cancelled"
        assert bridge.diagnostics["temporary_released"]
    finally:
        if timer:
            timer.cancel()
        bridge.close()


@pytest.mark.parametrize("failed_receipt", [False, True])
def test_receipt_settled_between_poll_timeout_and_worker_stop_is_preserved(failed_receipt):
    bridge = connection()
    bridge._enabled = bridge._ready = True
    bridge._generation = 1
    bridge._sessions["s1"] = "word"
    receipt = {"session": "s1", "operation": "compose1", "outcome": "applied", "affected_items": 1}

    class BoundaryFuture(Future):
        def result(self, timeout=None):
            if not self.done():
                if failed_receipt:
                    self.set_exception(Error(Code.OUTCOME_UNKNOWN, "Synthetic unconfirmed receipt"))
                else:
                    self.set_result(receipt)
                bridge._stopped.set()
                raise FutureTimeout()
            return super().result(timeout)

    def dispatch(request):
        request.sent = True
        request.future = BoundaryFuture()

    bridge._queue = SimpleNamespace(put_nowait=dispatch)
    bridge._loop = SimpleNamespace(call_soon_threadsafe=lambda callback, request: callback(request))
    bridge.disconnect = lambda: pytest.fail("A settled receipt must not be replaced by disconnect/unknown")
    arguments = COMPOSE.arguments.model_validate(ARGS)
    if failed_receipt:
        with pytest.raises(Error) as caught:
            bridge.call(COMPOSE, arguments, expected=bridge.exposure, operation="compose1", cancellation=CancellationToken())
        assert caught.value.code == Code.OUTCOME_UNKNOWN
    else:
        assert bridge.call(COMPOSE, arguments, expected=bridge.exposure, operation="compose1", cancellation=CancellationToken()) == receipt


@pytest.mark.parametrize("code", [Code.OUTCOME_UNKNOWN, Code.INVALID_OUTPUT])
@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_failed_worker_receipt_waits_for_cleanup_and_keeps_its_original_error(code, cleanup_failure):
    bridge = connection()
    bridge._enabled = bridge._ready = True
    bridge._generation = 1
    bridge._sessions["s1"] = "word"
    stop = Event()
    worker = Thread(target=stop.wait)
    bridge._thread = worker
    worker.start()
    failure = Error(code, "Synthetic failed worker receipt")
    calls = []

    def dispatch(request):
        if request is None:
            stop.set()
            return
        calls.append(request)
        request.sent = True
        bridge._ready = bridge._enabled = False
        request.future.set_exception(failure)

    def abort():
        raise OSError("Synthetic cleanup failure")

    bridge._queue = SimpleNamespace(put_nowait=dispatch)
    bridge._loop = SimpleNamespace(call_soon_threadsafe=lambda callback, request: callback(request))
    if cleanup_failure:
        bridge._transport = SimpleNamespace(abort=abort)
    contract = COMPOSE if code == Code.OUTCOME_UNKNOWN else next(t for t in OFFICE_TOOLS if t.name == "office.read")
    arguments = contract.arguments.model_validate(ARGS if contract == COMPOSE else {"session": "s1"})
    try:
        with pytest.raises(Error) as caught:
            bridge.call(contract, arguments, expected=bridge.exposure, operation="failed1", cancellation=CancellationToken())
        assert caught.value is failure
        assert len(calls) == 1 and not bridge.exposure.ready
        if cleanup_failure:
            assert bridge.diagnostics["confirmation_cleanup_failed"] is True
        else:
            assert not worker.is_alive()
    finally:
        stop.set()
        worker.join(2)
        bridge._transport = None
        bridge.close()
    assert not worker.is_alive()
