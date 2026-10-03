"""Opt-in fixed routing evaluation and actual frontend prompt integration."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.inference.protocol import native_chat_messages
from app.runtime.skills import SkillRegistry, select_skill
from app.runtime.skills.selection import SELECTOR_SYSTEM_PROMPT
from app.settings.agent import AgentFeatureConfig
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from app.state.storage import JsonStore
from tests.fixtures.skill_routing import CANDIDATES, FRONTEND_BODY, ROUTING_CASES


pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("ORSI_RUN_SKILL_SELECTION_LIVE") != "1",
    reason="Opt-in Qwen 14B fixed skill-routing evaluation and integration",
)


def test_qwen_fixed_44_case_accuracy_and_frontend_modes(tmp_path):
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=tmp_path / "selection.json")
    backend = LlamaServerInferenceEngine(catalog.configuration("Qwen314BQ4KM.gguf"))
    physical, records, answer_requests = [], [], []
    actual_request = backend._request_completion
    def audit(payload):
        router = payload["messages"][0]["content"] == SELECTOR_SYSTEM_PROMPT
        if router:
            assert "tools" not in payload and len(payload["messages"]) == 2
            data = json.loads(payload["messages"][1]["content"])
            assert set(data) == {"catalog", "request"}
            assert all(set(item) == {"name", "description"} for item in data["catalog"])
            assert FRONTEND_BODY not in payload["messages"][1]["content"]
        else:
            answer_requests.append(deepcopy(payload["messages"]))
        completion = actual_request(payload)
        usage = completion.get("usage", {})
        physical.append({"request_kind": "selector" if router else "answer",
                         "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                         "finish_reason": completion.get("choices", [{}])[0].get("finish_reason"),
                         "skill_sections": payload["messages"][0]["content"].count("\nACTIVE SKILL\n"),
                         "tools_hash": sha256(json.dumps(payload.get("tools", []), sort_keys=True).encode()).hexdigest()})
        return completion
    backend._request_completion = audit
    summary = {"schema_version": 1, "model_id": "Qwen314BQ4KM.gguf", "passed": False, "routing": records,
               "physical_requests": physical, "frontend_modes": []}
    artifact = JsonStore(PATHS.state / "test-artifacts/skill-phase3-2-live.json")
    service, process = None, None
    try:
        backend.prepare()
        process = backend._process
        for case in ROUTING_CASES:
            selection = select_skill(backend, candidates=CANDIDATES, request=case.request)
            record = {"case_id": case.case_id, "category": case.category, "obvious": case.obvious,
                      "expected": case.expected, "selected": selection.name,
                      "correct": selection.name == case.expected, "selection": asdict(selection)}
            records.append(record)
            artifact.save(summary)
            print(json.dumps({key: value for key, value in record.items() if key != "selection"}), flush=True)
        obvious = [record for record in records if record["obvious"]]
        ambiguous = [record for record in records if not record["obvious"]]
        summary.update({"obvious_correct": sum(r["correct"] for r in obvious), "obvious_total": len(obvious),
                        "ambiguous_none": sum(r["selected"] is None for r in ambiguous),
                        "ambiguous_total": len(ambiguous), "effective_context": backend.context_length,
                        "effective_output_reserve": backend.max_response_tokens})
        scope = tmp_path / "skills"
        for candidate in CANDIDATES:
            folder = scope / candidate.name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(
                "---\nname: " + candidate.name + "\ndescription: " + candidate.description + "\n---\n" +
                (FRONTEND_BODY if candidate.name == "design-taste-frontend" else "Use concise domain guidance."), encoding="utf-8")
        registry = SkillRegistry(global_root=scope)
        registry.discover()
        runtime = build_agent_runtime(backend, config=AgentFeatureConfig(filesystem_stat_enabled=True),
            portable_root=tmp_path, state_directory=tmp_path / "state")
        service = ConversationService(backend, ConversationStore(tmp_path / "chat.json"), agent_runtime=runtime,
            portable_root=tmp_path, skill_registry=registry, automatic_skills_enabled=False)
        for mode in ("without", "explicit", "automatic"):
            service.new_session()
            service.automatic_skills_enabled = mode == "automatic"
            if mode == "explicit":
                service.activate_skill("design-taste-frontend")
            begin = len(physical)
            reply = service.run(ROUTING_CASES[0].request)
            request = answer_requests[-1]
            native_chat_messages(service._model_messages(), runtime.registry.model_definitions())
            sections = request[0]["content"].count("\nACTIVE SKILL\n")
            assert sections == (0 if mode == "without" else 1)
            assert request[-1] == {"role": "user", "content": ROUTING_CASES[0].request}
            marker = str(reply).lstrip().removeprefix("**").startswith("FRONTEND-GUIDANCE:")
            assert marker == (mode != "without")
            if mode != "without":
                assert service.active_skill.name == "design-taste-frontend"
            mode_requests = deepcopy(physical[begin:])
            answers = [r for r in mode_requests if r["request_kind"] == "answer"]
            assert len(answers) == 1
            assert sum(r["request_kind"] == "selector" for r in mode_requests) == (1 if mode == "automatic" else 0)
            summary["frontend_modes"].append({"mode": mode, "selection": asdict(service.skill_selection),
                                              "style_marker": marker, "requests": mode_requests})
            artifact.save(summary)
        answer_hashes = {r["tools_hash"] for r in physical if r["request_kind"] == "answer"}
        assert len(answer_hashes) == 1
        assert summary["obvious_correct"] / summary["obvious_total"] >= 0.9
        assert summary["ambiguous_none"] == summary["ambiguous_total"]
        summary["passed"] = True
    finally:
        if service is not None:
            service.shutdown()
        else:
            backend.close()
        summary["owned_server_exited"] = process is None or process.poll() is not None
        artifact.save(summary)
        assert summary["owned_server_exited"]
