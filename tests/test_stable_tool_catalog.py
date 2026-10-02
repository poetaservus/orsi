"""Exercise confirmations through the real registry, approval and turn layers."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows host-write adapter")
LIST_PROMPT = "can you list me the standalone .txt files i have on my desktop? the ones that are not in a folder"
DELETE_PROMPT = "you can delete all of them"


class ConfirmationModel(InferenceEngine):
    def __init__(self, desktop):
        self.desktop = desktop
        self.requests = []

    def respond(self, messages):
        raise AssertionError("Use the structured tool boundary")

    def respond_with_capabilities(self, messages, capabilities):
        self.requests.append((messages, tuple(c.name for c in capabilities)))
        latest_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if messages[-1]["role"] == "capability" and not messages[-1]["result"]["success"]:
            return ModelResponse.text("The requested operation was denied.")
        if latest_user == LIST_PROMPT:
            if messages[-1]["role"] == "capability":
                return ModelResponse.text("The standalone files are one.txt and two.txt.")
            return self.call("filesystem.list", {"path": str(self.desktop)})
        if latest_user == DELETE_PROMPT:
            return ModelResponse.text("Please confirm moving those files to the Recycle Bin.")
        if latest_user in ("confirmed", "you're authorized to do it"):
            if "filesystem.trash" not in {c.name for c in capabilities}:
                return ModelResponse.text("I cannot delete files.")
            remaining = [p for p in self.desktop.glob("*.txt")]
            if remaining:
                return self.call("filesystem.trash", {"path": str(sorted(remaining)[0])})
            return ModelResponse.text("The approved files were sent to the Recycle Bin.")
        return ModelResponse.text("The available tools include writing, moving and Recycle Bin operations.")

    @staticmethod
    def call(name, arguments):
        return ModelResponse.calls((ModelCapabilityCall(
            provider_call_id="call-0", capability=name, arguments=arguments),))


def service_for(root, model, flags):
    portable = root / "portable"
    portable.mkdir(exist_ok=True)
    policy = HostAccessPolicy.full_local(application_root=portable,
        user_home=root / "home", acknowledged=True)
    runtime = build_agent_runtime(model, config=flags, portable_root=portable,
        state_directory=root / "state", host_access_policy=policy)
    return ConversationService(model, ConversationStore(root / "conversation.json"),
        agent_runtime=runtime, portable_root=portable, host_access_policy=policy)


@pytest.mark.parametrize("confirmation", ["confirmed", "you're authorized to do it"])
@pytest.mark.parametrize("approval", ["approve", "deny", "cancel"])
def test_confirmation_keeps_tools_but_never_bypasses_operation_approval(
    tmp_path, monkeypatch, confirmation, approval,
):
    desktop = tmp_path / "home" / "Desktop"
    desktop.mkdir(parents=True)
    targets = [desktop / "one.txt", desktop / "two.txt"]
    for target in targets:
        target.write_bytes(b"synthetic fixture\r\n")
    (desktop / "nested").mkdir()
    nested = desktop / "nested" / "keep.txt"
    nested.write_bytes(b"keep this nested file")
    mutations = []

    def fake_recycle(path, cancellation):
        cancellation.raise_if_cancelled()
        assert path in targets
        mutations.append(path)
        path.unlink()  # Only synthetic fixtures; production still uses the Recycle Bin.

    monkeypatch.setattr("app.capabilities.filesystem_trash.trash_file", fake_recycle)
    flags = AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_list_enabled=True,
        filesystem_read_text_enabled=True, filesystem_write_text_enabled=True,
        filesystem_move_enabled=True, filesystem_trash_enabled=True, full_local_read_enabled=True)
    model = ConfirmationModel(desktop)
    service = service_for(tmp_path, model, flags)
    seen_approvals = []

    def review(record):
        assert record.capability == "filesystem.trash" and Path(record.resource) in targets
        assert Path(record.resource).read_bytes() == b"synthetic fixture\r\n"
        seen_approvals.append(record)
        if approval == "cancel":
            service.cancel_current_task()
        else:
            service.resolve_approval(record.approval_id, approval == "approve")

    service.set_approval_requester(review)
    try:
        service.run(LIST_PROMPT)
        service.run(DELETE_PROMPT)
        assert not mutations and not seen_approvals
        service.run(confirmation)
        expected = service.agent_capabilities
        assert all(names == expected for _, names in model.requests)
        assert all("filesystem.trash" in messages[0]["content"] for messages, _ in model.requests)
        assert nested.read_bytes() == b"keep this nested file"
        if approval == "approve":
            assert mutations == targets and len(seen_approvals) == 2
            assert all(not p.exists() for p in targets)
            settled = service.store.turns()[-1].settled_calls
            assert len(settled) == 2 and all(s.result.success for s in settled)
        else:
            assert not mutations and len(seen_approvals) == 1
            assert all(p.read_bytes() == b"synthetic fixture\r\n" for p in targets)
        if approval == "cancel":
            assert service.store.turns()[-1].outcome.status.value == "cancelled"
        service.run("list me the tools you have")
        assert model.requests[-1][1] == expected
    finally:
        service.shutdown()

    # Match startup: reconcile durable outcomes, archive them, then start fresh.
    reopened_model = ConfirmationModel(desktop)
    reopened = service_for(tmp_path, reopened_model, flags)
    try:
        reopened.new_session(preserve_history=True)
        reopened.run("list me the tools you have")
        assert reopened_model.requests[-1][1] == expected
        assert not reopened.store.turns()[-1].settled_calls
        assert mutations == (targets if approval == "approve" else [])
    finally:
        reopened.shutdown()
