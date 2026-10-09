"""Source sufficiency at the existing read bounds and native edit boundary."""
from copy import deepcopy
import hashlib
import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.capabilities.contracts import CapabilityContext, CapabilityErrorCode
from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
from app.conversation.orchestrator import ConversationService
from app.conversation.recovery import recover_context_request
from app.conversation.store import ConversationStore
from app.inference.engine import InferenceEngine
from app.inference.hybrid import HybridInferenceEngine
from app.inference.protocol import ModelCapabilityCall, ModelResponse
from app.runtime.cancellation import CancellationSource
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig
from tests.fixtures.source_reads import python_source_fixture


def read_file(target, **bounds):
    return FilesystemReadTextCapability().invoke(
        {"path": str(target), **bounds},
        CapabilityContext(call_id="source-read", session_id="source-session", turn_id="source-turn",
            portable_root=target.parent, allowed_read_roots=(target.parent,),
            cancellation=CancellationSource().token),
    ).output


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bounds,byte_cut,line_cut,has_digest", [
    ({}, True, True, False),
    ({"max_bytes": 65536}, False, True, True),
    ({"max_lines": 1000}, True, False, False),
])
def test_truncated_source_identifies_larger_supported_read(tmp_path, newline, bounds,
                                                         byte_cut, line_cut, has_digest):
    target = tmp_path / "main.py"
    raw = python_source_fixture(newline)
    target.write_bytes(raw)
    prefix = read_file(target, **bounds)
    repeated = read_file(target, **bounds)
    assert prefix == repeated  # An identical prefix cannot recover the unseen method.
    assert prefix["truncated_by_bytes"] is byte_cut
    assert prefix["truncated_by_lines"] is line_cut
    assert prefix["source_complete"] is False
    assert "draw_overlay" not in prefix["text"]
    assert "max_bytes=65536 and max_lines=1000" in prefix["read_hint"]
    assert "Repeating" in prefix["read_hint"]
    assert prefix["sha256"] == (hashlib.sha256(raw).hexdigest() if has_digest else None)

    complete = read_file(target, max_bytes=65536, max_lines=1000)
    assert complete["source_complete"] is True and complete["read_hint"] is None
    assert not complete["truncated_by_bytes"] and not complete["truncated_by_lines"]
    assert complete["text"].encode("utf-8") == raw
    assert complete["lines_returned"] == 453
    assert complete["sha256"] == hashlib.sha256(raw).hexdigest()
    assert complete["text"].splitlines()[330] == "    return sum(values) - 1"
    assert complete["path"] == str(target.resolve())


@pytest.mark.parametrize("raw,byte_cut,line_cut", [
    (b"# padding\n" * 7000 + b"def missing_target(): pass\n", True, True),
    (b"# p\n" * 1000 + b"def missing_target(): pass\n", False, True),
], ids=["byte-ceiling", "line-ceiling"])
def test_supported_ceiling_reports_actionable_limitation(tmp_path, raw, byte_cut, line_cut):
    target = tmp_path / "large.py"
    target.write_bytes(raw)
    output = read_file(target, max_bytes=65536, max_lines=1000)
    assert output["source_complete"] is False
    assert output["truncated_by_bytes"] is byte_cut
    assert output["truncated_by_lines"] is line_cut
    assert "missing_target" not in output["text"]
    assert "stop and request a smaller source file" in output["read_hint"]
    assert "does not support range reads" in output["read_hint"]
    assert output["sha256"] == (None if byte_cut else hashlib.sha256(raw).hexdigest())


def test_line_bound_can_expand_even_when_byte_ceiling_is_reached(tmp_path):
    target = tmp_path / "large.py"
    target.write_bytes(b"# padding\n" * 7000)
    output = read_file(target, max_bytes=65536, max_lines=200)
    assert output["truncated_by_bytes"] and output["truncated_by_lines"]
    assert "max_bytes=65536 and max_lines=1000" in output["read_hint"]


@pytest.mark.parametrize("max_bytes,expected", [(1, ""), (2, "é"), (3, "é")])
def test_byte_truncation_retains_valid_utf8_without_invented_digest(tmp_path, max_bytes, expected):
    target = tmp_path / "utf8.py"
    target.write_bytes("éπ\r\n".encode("utf-8"))
    output = read_file(target, max_bytes=max_bytes)
    assert output["text"] == expected
    assert not output["source_complete"] and output["truncated_by_bytes"]
    assert output["sha256"] is None


def test_empty_source_is_complete(tmp_path):
    target = tmp_path / "empty.py"
    target.write_bytes(b"")
    output = read_file(target)
    assert output["source_complete"] and output["read_hint"] is None
    assert output["sha256"] == hashlib.sha256(b"").hexdigest()


def test_context_excerpt_cannot_claim_complete_source(tmp_path):
    target = tmp_path / "main.py"
    target.write_bytes(python_source_fixture())
    output = read_file(target, max_bytes=65536, max_lines=1000)
    messages = [{"role": "user", "content": "Fix draw_overlay in main.py."},
        {"role": "capability", "result": {"capability": "filesystem.read_text",
            "success": True, "output": output, "metadata": {}}}]
    recovered = recover_context_request(GroundedEditModel(target), messages)
    result = recovered.messages[-1]["result"]
    assert result["metadata"]["context_projection"]["complete"] is False
    assert result["output"]["source_complete"] is False
    assert "context limitation" in result["output"]["read_hint"]
    assert "characters omitted" in result["output"]["text"]
    assert result["output"]["sha256"] == output["sha256"]
    assert output["source_complete"] and output["read_hint"] is None
    assert output["text"].encode("utf-8") == target.read_bytes()


def test_source_read_preserves_existing_default_and_ceiling_contract():
    schema = FilesystemReadTextCapability.arguments_model.model_json_schema()
    properties = schema["properties"]
    assert properties["max_bytes"]["default"] == 16384
    assert properties["max_lines"]["default"] == 200
    assert properties["max_bytes"]["maximum"] == 65536
    assert properties["max_lines"]["maximum"] == 1000
    assert "max_bytes=65536 and max_lines=1000" in FilesystemReadTextCapability.description


class GroundedEditModel(InferenceEngine):
    # These are adapter/approval checks, not a real local-model context qualification.
    context_length = 200000
    max_response_tokens = 4096

    def __init__(self, target, *, stale=False, missing=False):
        self.target, self.stale, self.missing = target, stale, missing
        self.requests = []
        self.counter = 0

    def respond(self, messages):
        raise AssertionError("Use the structured boundary.")

    def respond_with_capabilities(self, messages, capabilities):
        self.requests.append(deepcopy(messages))
        self.counter += 1
        latest = messages[-1]
        if latest.get("role") != "capability":
            tool, arguments = "filesystem.read_text", {"path": str(self.target)}
        elif latest["result"]["capability"] == "filesystem.read_text":
            output = latest["result"]["output"]
            if not output["source_complete"]:
                assert "max_bytes=65536 and max_lines=1000" in output["read_hint"]
                tool, arguments = "filesystem.read_text", {
                    "path": output["path"], "encoding": output["encoding"],
                    "max_bytes": 65536, "max_lines": 1000,
                }
            else:
                # Construct the patch from the actual current tool text, never a preset excerpt.
                lines = output["text"].splitlines(keepends=True)
                index = next(i for i, line in enumerate(lines) if line.startswith("def draw_overlay("))
                excerpt = "".join(lines[index:index + 2])
                assert index == 329
                tool, arguments = "filesystem.edit_text", {
                    "path": output["path"], "old_text": excerpt,
                    "new_text": excerpt.replace("sum(values) - 1", "sum(values)"),
                    "expected_sha256": output["sha256"],
                }
                if self.stale:
                    self.target.write_bytes(self.target.read_bytes().replace(b"fixture 001", b"fixture 000"))
                if self.missing:
                    arguments["old_text"] = excerpt.replace("sum(values) - 1", "sum(values) - 2")
        else:
            return ModelResponse.text("Source inspection finished.")
        return ModelResponse.calls((ModelCapabilityCall(provider_call_id=f"source-{self.counter}",
            capability=tool, arguments=arguments),))


@pytest.mark.skipif(os.name != "nt", reason="Native Windows edit/approval adapter.")
@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("failure", [None, "stale", "missing"])
def test_below_line_200_edit_uses_returned_revision_and_native_approval(tmp_path, mode, newline, failure):
    target = tmp_path / "main.py"
    original = python_source_fixture(newline)
    target.write_bytes(original)
    portable = tmp_path / "portable"
    portable.mkdir()
    backend = GroundedEditModel(target, stale=failure == "stale", missing=failure == "missing")
    inference = HybridInferenceEngine(local=backend if mode == "local" else None,
        cloud=backend if mode == "cloud" else None, default_mode=mode, fallback_to_local=False)
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path, acknowledged=True)
    runtime = build_agent_runtime(inference, config=AgentFeatureConfig(
        filesystem_stat_enabled=True, filesystem_read_text_enabled=True,
        filesystem_edit_text_enabled=True, full_local_read_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(inference, ConversationStore(portable / "chat.json"),
        agent_runtime=runtime, portable_root=portable, allowed_read_roots=policy.permission_roots(),
        host_access_policy=policy)
    approvals = []

    def approve(record):
        assert record.resource == str(target.resolve()) and target.read_bytes() == original
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)

    service.set_approval_requester(approve)
    try:
        service.run(f'Fix draw_overlay in "{target}". Preserve unrelated source and line endings.')
        settled = service._turn_result.settled_calls
        assert [item.call.capability for item in settled] == [
            "filesystem.read_text", "filesystem.read_text", "filesystem.edit_text"]
        assert not settled[0].result.output["source_complete"]
        source = settled[1].result.output
        edit = settled[2]
        assert source["source_complete"]
        if failure == "missing":
            assert edit.call.arguments["old_text"] not in source["text"]
        else:
            assert edit.call.arguments["old_text"] in source["text"]
        assert edit.call.arguments["expected_sha256"] == source["sha256"]
        model_source = backend.requests[2][-1]["result"]["output"]
        assert model_source == source  # The complete source reaches the planner unchanged.
        if failure:
            assert not edit.result.success and edit.result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
            assert ("digest" if failure == "stale" else "not found") in edit.result.error.message
            expected = original.replace(b"fixture 001", b"fixture 000") if failure == "stale" else original
            assert target.read_bytes() == expected and approvals == []
        else:
            assert edit.result.success and len(approvals) == 1
            assert target.read_bytes() == original.replace(b"sum(values) - 1", b"sum(values)")
            assert service.approval_status(approvals[0].approval_id) == "consumed"
            assert edit.result.output["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    finally:
        service.shutdown()
