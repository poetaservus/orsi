"""Office catalogs must work through the conversation layer, before model dispatch."""
import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.prompt import compact_agent_system_prompt
from app.conversation.store import ConversationStore
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.mcp.office_contracts import OFFICE_TOOLS
from app.security.host_access import HostReadScope
from app.settings.agent import AgentFeatureConfig
from tests.test_agent_runtime import ScriptedModel
from tests.test_office_mcp_connection import ROOT
from tests.test_office_mcp_excel import connection
from tests.test_office_mcp_live import execute


def test_compact_prompt_accepts_every_reviewed_office_tool():
    names = ("filesystem.stat", *(tool.name for tool in OFFICE_TOOLS))
    prompt = compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, names)
    assert all(name in prompt for name in names)


@pytest.mark.parametrize("names", [("office.unreviewed",), ("office.read", "office.read")])
def test_compact_prompt_still_rejects_unreviewed_and_duplicate_tools(names):
    with pytest.raises(ValueError, match="unsupported catalog"):
        compact_agent_system_prompt(HostReadScope.PORTABLE_ROOT, names)


@pytest.mark.skipif(os.name != "nt", reason="Windows owned MCP conversation integration")
def test_conversation_greeting_read_and_mode_changes_with_live_office_catalog(tmp_path):
    model = ScriptedModel([ModelResponse.text("Hello.")])
    model.mode = "cloud"
    model.context_length = 131_072
    bridge = connection()
    runtime = build_agent_runtime(model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True, conversation_context_enabled=True),
        portable_root=ROOT, state_directory=tmp_path,
        office_connection=bridge, office_resource_policy=bridge.resource_policy)
    service = ConversationService(model, ConversationStore(tmp_path / "conversation.json"),
        agent_runtime=runtime, portable_root=ROOT)
    try:
        assert service.run("hey") == "Hello."
        assert not any(d.name.startswith("office.") for d in model.definitions[-1])
        bridge.connect()
        document = bridge.list_documents()[0]
        bridge.select_document(document["document"])
        model.responses.append(ModelResponse.text("Hello again."))
        assert service.run("hey") == "Hello again."
        names = {d.name for d in model.definitions[-1]}
        assert {name for name in names if name.startswith("office.")} == {
            "office.documents", "office.attach", "office.read", "office.excel_edit", "office.revert", "office.save"}
        assert "conversation.read_turn" in names
        assert all(name in model.requests[-1][0]["content"] for name in names)
        assert bridge.diagnostics["tool_calls"] == 0  # Greetings never touch Office.

        attached = execute(runtime, "attach", {"application": "excel", "document": document["document"]}, "attach")
        model.responses.extend([ModelResponse.calls((ModelCapabilityCall(provider_call_id="read-cells",
            capability="office.read", arguments={"session": attached.output["session"], "target": "Sheet1!A1:A2"}),)),
            ModelResponse.text("The selected cells were read.")])
        assert service.run("Read A1:A2 in the selected workbook.") == "The selected cells were read."
        settled = service.store.turns()[-1].settled_calls
        assert len(settled) == 1 and settled[0].result.success
        assert settled[0].call.capability == "office.read"

        for mode in ("local", "cloud"):
            model.mode = mode
            model.responses.append(ModelResponse.text("Ready."))
            assert service.run("hey") == "Ready."
            assert any(d.name.startswith("office.") for d in model.definitions[-1]) == (mode == "cloud")
        bridge.disconnect()
        model.responses.append(ModelResponse.text("Disconnected."))
        assert service.run("hey") == "Disconnected."
        assert not any(d.name.startswith("office.") for d in model.definitions[-1])
    finally:
        service.shutdown()
    assert not bridge.diagnostics["worker_alive"]
