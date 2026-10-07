"""Opt-in real 14B document smoke; synthetic material and isolated conversation state."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.settings.agent import load_agent_feature_config
from app.security.host_access import HostAccessPolicy
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from tests.test_attachment_processing import make_pdf


pytestmark = pytest.mark.skipif(os.environ.get("ORSI_RUN_DOCUMENT_INPUT_LIVE") != "1",
                               reason="Opt-in accepted 14B document input smoke")


def test_accepted_14b_document_followup_restore_pdf_and_native_continuation(tmp_path):
    if os.name != "nt":
        pytest.skip("Native Windows local model smoke")
    processes = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if '"llama-server.exe"' in processes.stdout.lower():
        pytest.skip("An existing local model server is owned by another session")
    profile = (PATHS.config / "model.json").read_bytes()
    config = load_model_config()
    assert Path(config.model_path).name == "Qwen314BQ4KM.gguf"
    engine = LlamaServerInferenceEngine(config)
    physical, owned = [], None
    original = engine._request_completion

    def audit(payload):
        result = original(payload)
        usage = result.get("usage", {})
        physical.append({"input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"), "tool_count": len(payload.get("tools", [])),
            "finish_reason": result["choices"][0].get("finish_reason")})
        return result

    engine._request_completion = audit
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
    runtime = None
    passed = False
    try:
        engine.prepare()
        owned = engine._process
        assert engine.context_length == 16384 and engine.max_response_tokens == 4096
        ref = service.store.attachment_store.import_bytes(b"Project codename: NORTHSTAR\nShipment count: 37\n", name="report.txt")
        answer = service.run("Read the attached document. Reply with the project codename and shipment count.", attachments=[ref])
        assert "NORTHSTAR" in answer.upper() and "37" in answer
        answer = service.run("What was the shipment count in the previous attachment? Reply with just the number.")
        assert "37" in answer
        restored = ConversationService(engine, ConversationStore(tmp_path / "chat.json"))
        answer = restored.run("What was the project codename in the attached report? Reply with just the codename.")
        assert "NORTHSTAR" in answer.upper()
        pdf = restored.store.attachment_store.import_bytes(make_pdf(text="Contingency colour: AMBER"), name="colour.pdf")
        answer = restored.run("Read the attached PDF. What is the contingency colour? Reply with just the colour.", attachments=[pdf])
        assert "AMBER" in answer.upper()
        portable = tmp_path / "portable"
        portable.mkdir()
        (portable / "fixture.txt").write_text("Synthetic stat fixture", encoding="utf-8")
        flags = load_agent_feature_config()
        policy = (HostAccessPolicy.full_local(application_root=portable, user_home=portable, acknowledged=True)
                  if flags.full_local_read_enabled else HostAccessPolicy.portable_root(portable))
        runtime = build_agent_runtime(engine, config=flags, portable_root=portable,
                                      state_directory=portable / "state", host_access_policy=policy)
        agent = ConversationService(engine, ConversationStore(portable / "chat.json"),
                                    agent_runtime=runtime, portable_root=portable, host_access_policy=policy)
        agent.set_approval_requester(lambda record: agent.resolve_approval(record.approval_id, False))
        note = agent.store.attachment_store.import_bytes(b"Dispatch count: 82\n", name="dispatch.txt")
        answer = agent.run("Check fixture.txt with filesystem.stat, then give the dispatch count from the attached document.", attachments=[note])
        assert "82" in answer
        assert any(c.call.capability == "filesystem.stat" for c in agent.store.turns()[0].settled_calls)
        assert agent.context_budget().fits
        assert (PATHS.config / "model.json").read_bytes() == profile
        assert all(p["finish_reason"] in {"stop", "tool_calls"} for p in physical)
        passed = True
    finally:
        engine.close()
        if runtime is not None:
            runtime.shutdown()
        released = owned is None or owned.poll() is not None
        summary = {"scope": "local_document_input_phase3a", "passed": passed,
            "model_id": Path(config.model_path).name, "context_length": engine.context_length,
            "output_reserve": engine.max_response_tokens, "physical_requests": physical,
            "owned_process_released": released, "profile_unchanged": (PATHS.config / "model.json").read_bytes() == profile}
        (tmp_path / "live-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        assert released
