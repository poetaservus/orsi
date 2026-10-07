"""Read/edit/read workflows progress without relaxing no-progress loop stops."""
import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.contracts import AgentRunStatus
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.hybrid import HybridInferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig
from tests.test_agent_runtime import ScriptedModel


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows read/write adapters")


def call(tool, arguments, identity):
    return ModelResponse.calls((ModelCapabilityCall(
        provider_call_id=f"call-{identity}", capability=tool, arguments=arguments),))


def read(path, identity, max_bytes=65536):
    return call("filesystem.read_text", {
        "path": str(path), "encoding": "utf-8", "max_bytes": max_bytes, "max_lines": 1000,
    }, identity)


def change(path, identity, version, tool="filesystem.edit_text"):
    arguments = {"path": str(path)}
    if tool == "filesystem.edit_text":
        arguments.update(old_text=f"version {version}", new_text=f"version {version + 1}")
    else:
        arguments.update(text=f"version {version + 1}\n" + "tail\n" * 100)
    return call(tool, arguments, identity)


@pytest.fixture
def scenario(tmp_path):
    portable = tmp_path / "portable"
    portable.mkdir()
    target = tmp_path / "target.py"
    other = tmp_path / "other.py"
    original = "version 0\n" + "tail\n" * 100
    target.write_text(original, encoding="utf-8", newline="")
    other.write_text(original, encoding="utf-8", newline="")
    policy = HostAccessPolicy.full_local(
        application_root=portable, user_home=tmp_path, acknowledged=True)
    services = []

    def build(responses, mode="local", approve=True):
        backend = ScriptedModel(responses)
        inference = HybridInferenceEngine(local=backend if mode == "local" else None,
            cloud=backend if mode == "cloud" else None, default_mode=mode, fallback_to_local=False)
        runtime = build_agent_runtime(inference, config=AgentFeatureConfig(
            filesystem_stat_enabled=True, filesystem_read_text_enabled=True,
            filesystem_edit_text_enabled=True, filesystem_write_text_enabled=True,
            full_local_read_enabled=True), portable_root=portable,
            state_directory=portable / "state", host_access_policy=policy)
        service = ConversationService(inference, ConversationStore(portable / "history.json"),
            agent_runtime=runtime, portable_root=portable,
            allowed_read_roots=policy.permission_roots(), host_access_policy=policy)
        approvals = []

        def decide(record):
            approvals.append(record)
            service.resolve_approval(record.approval_id, approve)

        service.set_approval_requester(decide)
        services.append(service)
        return service, backend, approvals

    yield target, other, original, build
    for service in services:
        service.shutdown()


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("tool,max_bytes", [
    ("filesystem.edit_text", 65536), ("filesystem.edit_text", 4),
    ("filesystem.write_text", 65536),
])
def test_three_identical_reads_after_two_approved_changes_complete(scenario, mode, tool, max_bytes):
    target, _, _, build = scenario
    service, model, approvals = build([
        read(target, 1, max_bytes), change(target, 2, 0, tool), read(target, 3, max_bytes),
        change(target, 4, 1, tool), read(target, 5, max_bytes), ModelResponse.text("Done"),
    ], mode=mode)
    assert service.run("Fix the file and inspect each saved version.") == "Done"
    assert target.read_text(encoding="utf-8").startswith("version 2\n")
    assert len(approvals) == 2
    assert all(service.approval_status(r.approval_id) == "consumed" for r in approvals)
    result = service._turn_result
    assert result.status == AgentRunStatus.COMPLETED and result.capability_calls == 5
    assert len(model.requests) == 6 and len(result.settled_calls) == 5
    reads = [s.result.output for s in result.settled_calls if s.call.capability == "filesystem.read_text"]
    assert len(reads) == 3
    if max_bytes == 65536:
        assert [r["text"].splitlines()[0] for r in reads] == ["version 0", "version 1", "version 2"]
        assert len({r["sha256"] for r in reads}) == 3
    else:
        assert all(r["sha256"] is None and r["truncated_by_bytes"] for r in reads)


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("intervening", ["nothing", "unrelated_edit", "noop_write", "failed_edit", "denied_edit"])
def test_no_progress_still_stops_before_third_read(scenario, mode, intervening):
    target, other, original, build = scenario
    responses = [read(target, 1), read(target, 2)]
    if intervening == "unrelated_edit":
        responses.append(change(other, 3, 0))
    elif intervening == "noop_write":
        responses.append(call("filesystem.write_text", {"path": str(target), "text": original}, 3))
    elif intervening == "failed_edit":
        responses.append(change(target, 3, 99))
    elif intervening == "denied_edit":
        responses.append(change(target, 3, 0))
    responses.append(read(target, 4))
    service, model, _ = build(responses, mode=mode, approve=intervening != "denied_edit")
    with pytest.raises(RuntimeError, match="repeating an identical capability call"):
        service.run("Inspect the file.")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert target.read_text(encoding="utf-8") == original
    assert len([s for s in service._turn_result.settled_calls if s.call.capability == "filesystem.read_text"]) == 2
    assert len(model.requests) == len(responses)


def test_changed_file_gets_only_two_reads_before_its_next_change(scenario):
    target, _, _, build = scenario
    service, _, _ = build([
        read(target, 1), change(target, 2, 0), read(target, 3), read(target, 4), read(target, 5),
    ])
    with pytest.raises(RuntimeError, match="repeating an identical capability call"):
        service.run("Inspect the saved version.")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert len(service._turn_result.settled_calls) == 4


def test_duplicate_reads_in_one_batch_still_stop_after_progress(scenario):
    target, _, _, build = scenario
    duplicates = ModelResponse.calls((read(target, 3).capability_calls[0], read(target, 4).capability_calls[0]))
    service, _, _ = build([read(target, 1), change(target, 2, 0), duplicates])
    with pytest.raises(RuntimeError, match="duplicate calls in one batch"):
        service.run("Inspect the saved version.")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert len(service._turn_result.settled_calls) == 2


def test_successful_edit_matches_canonical_result_paths_case_insensitively(scenario):
    target, _, _, build = scenario
    service, _, approvals = build([
        read(target, 1), read(target, 2), change(str(target).upper().replace("\\", "/"), 3, 0),
        read(target, 4), ModelResponse.text("Done"),
    ])
    assert service.run("Edit and reread the same file.") == "Done"
    assert len(approvals) == 1 and len(service._turn_result.settled_calls) == 4


def test_identical_replacement_after_truncated_reads_does_not_renew_allowance(scenario):
    target, _, original, build = scenario
    service, _, _ = build([
        read(target, 1, 4), read(target, 2, 4),
        call("filesystem.write_text", {"path": str(target), "text": original}, 3),
        read(target, 4, 4),
    ])
    with pytest.raises(RuntimeError, match="repeating an identical capability call"):
        service.run("Inspect the saved version.")
    assert service._turn_result.status == AgentRunStatus.REPEATED_CALL
    assert len(service._turn_result.settled_calls) == 3
