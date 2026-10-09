"""Mutation reports survive supporting reads; direct content displays stay grounded."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.capabilities.contracts import CapabilityResult, CapabilityFailure, CapabilityErrorCode
from app.conversation.result_grounding import grounded_text_read_answer
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from tests.test_agent_runtime import ScriptedModel


REPORT = "Changed main.py. I reread the saved source. Python and GUI tests were not run."
SOURCE = "def count(values):\r\n    return len(values)\r\n"


def observed(capability, success=True, output=None):
    call = ModelCapabilityCall(provider_call_id="result-" + capability.replace(".", "-"),
        capability=capability, arguments={"path": r"C:\fixture\main.py"})
    result = CapabilityResult(call_id=call.provider_call_id, capability=capability,
        success=success, output=output, duration_ms=0,
        error=None if success else CapabilityFailure(code=CapabilityErrorCode.PERMISSION_DENIED, message="Denied."))
    return call, result


def read_result():
    return observed("filesystem.read_text", output={"path": r"C:\fixture\main.py", "text": SOURCE})


@pytest.mark.parametrize("capability", ["filesystem.edit_text", "filesystem.write_text", "filesystem.copy",
    "filesystem.move", "filesystem.mkdir", "filesystem.trash"])
@pytest.mark.parametrize("success", [True, False])
def test_supporting_read_does_not_replace_mutation_or_failure_report(capability, success):
    result = grounded_text_read_answer("Fix main.py. Read current source and verify it. Report the checks.",
        REPORT, [observed(capability, success), read_result()])
    assert result is None


@pytest.mark.parametrize("user_text", ["Fix main.py and show its full contents.",
    "Fix main.py and display the updated file.", "Fix main.py and paste the saved text."])
def test_explicit_content_display_after_change_remains_grounded(user_text):
    result = grounded_text_read_answer(user_text, "Updated.",
        [observed("filesystem.edit_text"), read_result()])
    assert result.startswith("Updated.") and SOURCE in result


@pytest.mark.parametrize("user_text", [
    "Fix main.py and show which lines changed in the source.",
    "Fix main.py and show which checks ran on the saved text.",
    "Fix main.py and show the test report.",
])
def test_requested_change_or_check_summary_is_not_a_file_display(user_text):
    assert grounded_text_read_answer(user_text, REPORT,
        [observed("filesystem.edit_text"), read_result()]) is None


@pytest.mark.parametrize("user_text", ["Read main.py", "Show the file contents", "What does the file say?"])
def test_direct_reads_still_replace_missing_content(user_text):
    result = grounded_text_read_answer(user_text, "I read it.", [read_result()])
    assert SOURCE in result


@pytest.mark.skipif(os.name != "nt", reason="Native Windows edit/approval adapter.")
def test_actual_edit_read_report_is_returned_and_persisted(tmp_path):
    from app.agent.bootstrap import build_agent_runtime
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import AgentFeatureConfig
    target = tmp_path / "main.py"
    target.write_bytes(b"old\r\nkeep\r\n")
    portable = tmp_path / "portable"
    portable.mkdir()
    model = ScriptedModel([
        ModelResponse.calls((ModelCapabilityCall(provider_call_id="edit-1", capability="filesystem.edit_text",
            arguments={"path": str(target), "old_text": "old", "new_text": "new"}),)),
        ModelResponse.calls((ModelCapabilityCall(provider_call_id="read-1", capability="filesystem.read_text",
            arguments={"path": str(target)}),)), ModelResponse.text(REPORT),
    ])
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(model, config=AgentFeatureConfig(filesystem_stat_enabled=True,
        filesystem_read_text_enabled=True, filesystem_edit_text_enabled=True, full_local_read_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(model, ConversationStore(portable / "chat.json"), agent_runtime=runtime,
        portable_root=portable, allowed_read_roots=policy.permission_roots(), host_access_policy=policy)
    service.set_approval_requester(lambda record: service.resolve_approval(record.approval_id, True))
    try:
        answer = service.run("Fix main.py. Read current source and verify it. Report which checks ran.")
        assert str(answer) == REPORT
        assert target.read_bytes() == b"new\r\nkeep\r\n"
        reopened = type(service.store)(service.store.path)
        assert reopened.messages()[-1]["content"] == REPORT
        assert len(reopened.turns()[-1].settled_calls) == 2
    finally:
        service.shutdown()
