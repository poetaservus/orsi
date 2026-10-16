"""Focused Phase 3 discovery, binding, pagination and actual stdio checks."""
import asyncio
import json
from pathlib import Path
import sys

import pytest

from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError
from app.mcp.office_com import OfficeUnavailable
from app.mcp.office_connection import OfficeConnection
from app.mcp.office_contracts import OFFICE_TOOLS, AttachArguments, ReadArguments
from app.mcp.office_discovery import OfficeDiscovery, OfficeInstallation, discover_office
from app.mcp.office_live import LiveOffice, OfficeSTA
from app.mcp.stdio_transport import OwnedStdioTransport
from tests.fixtures.office_live_server import MemoryOffice
from tests.test_office_mcp_capabilities import OfflineModel, authorize, prepare, runtime_for
from tests.test_office_mcp_connection import ROOT


def tool(name):
    return next(value for value in OFFICE_TOOLS if value.name == "office." + name)


def service():
    live = LiveOffice(MemoryOffice)
    live.control("configure", {"applications": ["excel", "word"]})
    values = live.control("documents", {})["documents"]
    first = live.binding(document=values[0]["document"]["document"])
    authority = {"document": first["document"]["document"], "identity": first["identity"]}
    attached = live.call(tool("attach"), AttachArguments(application="excel", document=authority["document"]), authority)
    return live, authority, attached["session"]


def test_discovery_is_cached_across_connections_until_explicit_refresh():
    requests = []
    cache = OfficeDiscovery(lambda: requests.append(1) or [OfficeInstallation("word", "class", None)])
    assert cache.get() == cache.get()
    assert requests == [1]
    cache.get(refresh=True)
    assert requests == [1, 1]


def test_registry_checks_user_machine_both_views_and_validates_app_path(monkeypatch, tmp_path):
    import winreg
    executable = tmp_path / "EXCEL.EXE"
    executable.touch()
    calls = []

    class Key:
        def __init__(self, key):
            self.key = key
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def open_key(hive, key, reserved, access):
        calls.append((hive, key, access))
        return Key(key)

    def query(key, _):
        if key.key == r"Software\Classes\Excel.Application\CLSID":
            return "{00024500-0000-0000-C000-000000000046}", winreg.REG_SZ
        if key.key.endswith(r"App Paths\EXCEL.EXE"):
            return '"' + str(executable) + '"', winreg.REG_SZ
        raise FileNotFoundError()

    monkeypatch.setattr(winreg, "OpenKey", open_key)
    monkeypatch.setattr(winreg, "QueryValueEx", query)
    values = discover_office()
    assert len(values) == 1 and values[0].executable == executable.resolve()
    assert {c[0] for c in calls} == {winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE}
    assert {c[2] for c in calls} == {winreg.KEY_READ | winreg.KEY_WOW64_32KEY, winreg.KEY_READ | winreg.KEY_WOW64_64KEY}


def test_unsaved_sessions_remain_bound_when_other_document_changes():
    live, authority, session = service()
    live.backend.docs[1]["value"] = "other focused document"
    output = live.call(tool("read"), ReadArguments(session=session), authority)
    assert output["items"][0]["text"] == "alpha"
    assert not live.binding(session=session)["document"]["has_path"]
    assert output["snapshot"] in live.snapshots
    live.backend.docs.pop(0)
    with pytest.raises(OfficeUnavailable):
        live.call(tool("read"), ReadArguments(session=session), authority)


@pytest.mark.parametrize("text", ["a" * 10000, "\U0001f642" * 4000, '\"\\\n' * 2000], ids=["ascii", "unicode", "escaping"])
def test_reads_page_without_loss_and_respect_char_and_byte_limits(text):
    live, authority, session = service()
    live.backend.docs[0]["value"] = text
    cursor, result = None, ""
    while True:
        arguments = ReadArguments(session=session, cursor=cursor, max_chars=137, max_items=2)
        output = live.call(tool("read"), arguments, authority)
        tool("read").validate_result(arguments, output)
        result += "".join(item["text"] for item in output["items"])
        assert len(json.dumps(output, ensure_ascii=False).encode()) <= 16384
        cursor = output["cursor"]
        if cursor is None:
            break
    assert result == text


def test_changed_paged_region_and_cross_target_cursors_fail_closed():
    live, authority, session = service()
    first = live.call(tool("read"), ReadArguments(session=session, max_chars=2), authority)
    with pytest.raises(OfficeUnavailable):
        live.call(tool("read"), ReadArguments(session=session, cursor=first["cursor"], target="other"), authority)
    live.backend.docs[0]["value"] = "changed"
    with pytest.raises(OfficeUnavailable):
        live.call(tool("read"), ReadArguments(session=session, cursor=first["cursor"]), authority)


def test_saved_path_changes_invalidate_the_old_document_authority(tmp_path):
    live, authority, session = service()
    path = tmp_path / "synthetic.xlsx"
    path.touch()
    live.backend.docs[0]["path"] = str(path)
    with pytest.raises(OfficeUnavailable):
        live.call(tool("read"), ReadArguments(session=session), authority)


def test_all_automation_runs_and_releases_on_one_sta():
    async def run():
        sta = OfficeSTA(lambda: LiveOffice(MemoryOffice))
        try:
            await sta.invoke("control", "configure", {"applications": ["excel"]})
            values = await sta.invoke("control", "documents", {})
            assert len(values["documents"]) == 1
            backend = sta.service.backend
        finally:
            await sta.close()
        assert backend.closed
    asyncio.run(run())


def live_connection():
    return OfficeConnection(ROOT, backend=lambda: "cloud",
        discovery=OfficeDiscovery(lambda: (OfficeInstallation("excel", "fixture", None),
                                           OfficeInstallation("word", "fixture", None))),
        _transport_factory=lambda: OwnedStdioTransport(
            [sys.executable, "-m", "tests.fixtures.office_live_server"], root=ROOT))


def execute(runtime, name, arguments, operation):
    prepared = prepare(runtime, "office." + name, arguments, operation)
    return runtime.executor.execute(prepared, authorize(runtime, prepared))


def test_real_stdio_selected_document_flows_through_permissions_executor_and_private_channel(tmp_path):
    bridge = live_connection()
    runtime = runtime_for(bridge, tmp_path, policy=bridge.resource_policy)
    try:
        bridge.connect()
        assert {n for n in runtime.registry.model_visible_names if n.startswith("office.")} == {
            "office.documents", "office.attach", "office.read", "office.excel_edit", "office.word_edit", "office.word_compose", "office.save", "office.revert"}
        values = bridge.list_documents()
        assert len(values) == 2
        assert execute(runtime, "documents", {}, "empty").output["documents"] == []
        with pytest.raises(CapabilityExecutionError):
            prepare(runtime, "office.attach", {"application": "excel", "document": values[0]["document"]}, "unselected")
        bridge.select_document(values[0]["document"])
        attached = execute(runtime, "attach", {"application": "excel", "document": values[0]["document"]}, "attach")
        assert attached.success
        read = execute(runtime, "read", {"session": attached.output["session"], "max_chars": 2}, "read")
        assert read.success and read.output["items"][0]["text"] == "al"
        assert "path" not in json.dumps(read.output)
        assert bridge.discovery.runs == 1
        assert runtime.model.calls == 0
        assert bridge.diagnostics["tool_list_requests"] == 1
        assert bridge.diagnostics["tool_calls"] == 3
        assert "alpha" not in json.dumps([r.model_dump(mode="json") for r in runtime.executor.journal.records])
        invalid = execute(runtime, "read", {"session": attached.output["session"], "target": "invalid"}, "bad")
        assert not invalid.success and invalid.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
        assert "SECRET" not in invalid.error.message and bridge.exposure.ready
        bridge.disconnect()
        bridge.connect()
        assert bridge.discovery.runs == 1
        bridge.refresh()
        assert bridge.discovery.runs == 2
    finally:
        runtime.shutdown()
    assert not bridge.diagnostics["worker_alive"]


def test_private_saved_document_binding_obeys_existing_host_read_policy(tmp_path):
    live, authority, session = service()
    path = tmp_path / "outside-host-root.xlsx"
    path.touch()
    live.backend.docs[0]["path"] = str(path)
    binding = live.binding(session=session)
    from app.mcp.office_capabilities import OfficeResourceBinding
    bridge = live_connection()
    from app.security.host_access import HostAccessPolicy
    policy = HostAccessPolicy.portable_root(ROOT)
    from dataclasses import replace
    policy = replace(policy, protected_roots=(tmp_path,))
    runtime = runtime_for(bridge, tmp_path, policy=lambda *args:
                          OfficeResourceBinding(Path(binding["path"]), binding["identity"]))
    # Explicit protected roots exercise the existing read guard inside the checkout.
    try:
        bridge.connect()
        with pytest.raises(CapabilityExecutionError):
            from app.capabilities.contracts import CapabilityContext
            from app.runtime.cancellation import CancellationToken
            from app.security.permissions import prepare_capability_call
            context = CapabilityContext(call_id="denied", session_id="s", turn_id="t", portable_root=ROOT,
                allowed_read_roots=(ROOT,), host_access_policy=policy, cancellation=CancellationToken())
            prepare_capability_call(runtime.registry.resolve("office.attach"),
                {"application": "excel", "document": authority["document"]}, context)
    finally:
        runtime.shutdown()
