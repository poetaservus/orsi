"""Opt-in Qwen 14B prompt/style smoke; diagnostics retain no prompt content."""
from copy import deepcopy
from hashlib import sha256
import json
import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.inference.protocol import native_chat_messages
from app.runtime.skills import SkillRegistry
from app.settings.agent import AgentFeatureConfig
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from app.state.storage import JsonStore


pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("ORSI_RUN_SKILL_ACTIVATION_LIVE") != "1",
    reason="Opt-in real Qwen 14B skill activation smoke",
)


def test_qwen_receives_one_skill_obeys_style_and_user_priority_and_releases_server(tmp_path):
    scope = tmp_path / "skills" / "style"
    scope.mkdir(parents=True)
    body = "Prefix every conversational reply with Skill check: followed by a short greeting."
    (scope / "SKILL.md").write_text(
        "---\nname: style\ndescription: Synthetic style smoke.\n---\n" + body,
        encoding="utf-8")
    registry = SkillRegistry(global_root=scope.parent)
    registry.discover()
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=tmp_path / "selection.json")
    config = catalog.configuration("Qwen314BQ4KM.gguf")
    backend = LlamaServerInferenceEngine(config)
    runtime = build_agent_runtime(backend, config=AgentFeatureConfig(filesystem_stat_enabled=True),
                                  portable_root=tmp_path, state_directory=tmp_path / "state")
    service = ConversationService(backend, ConversationStore(tmp_path / "chat.json"),
                                  agent_runtime=runtime, portable_root=tmp_path, skill_registry=registry)
    requests = []
    actual_completion = backend._request_completion

    def inspect_request(payload):
        # Inspect the exact native request in memory; no prompts/keys enter diagnostics.
        requests.append(deepcopy(payload))
        return actual_completion(payload)

    backend._request_completion = inspect_request
    process = None
    summary = {"schema_version": 1, "model_id": "Qwen314BQ4KM.gguf", "passed": False}
    try:
        backend.prepare()
        process = backend._process
        baseline = service.run("Give a short greeting.")
        assert not baseline.startswith("Skill check:")
        baseline_tools = deepcopy(requests[-1]["tools"])
        service.new_session()
        service.activate_skill("style")
        styled = service.run("Give a short greeting.")
        assert styled.startswith("Skill check:")
        assert requests[-1]["tools"] == baseline_tools
        messages = requests[-1]["messages"]
        system = messages[0]["content"]
        assert system.count("\nACTIVE SKILL\n") == system.count("\nEND ACTIVE SKILL\n") == 1
        encoded = system.split("\nACTIVE SKILL\n", 1)[1].split("\nEND ACTIVE SKILL\n", 1)[0]
        assert json.loads(encoded) == {"name": "style", "instructions": body}
        if os.environ.get("ORSI_SHOW_SKILL_TEST_PROMPT") == "1":
            # Only this fixed synthetic fixture may be displayed for manual review.
            print("Qwen native system prompt:\n" + system, flush=True)
        assert messages[-1] == {"role": "user", "content": "Give a short greeting."}
        assert native_chat_messages(service._model_messages(), runtime.registry.model_definitions())
        service.new_session()
        service.activate_skill("style")
        user_priority = service.run("Reply exactly USER-WINS. Do not add any prefix or greeting.")
        exact_user_output = user_priority == "USER-WINS."
        # The priority smoke checks removal of the skill's prefix/greeting. Keep
        # the stricter punctuation observation separate rather than hiding it.
        assert user_priority in {"USER-WINS", "USER-WINS."}
        assert requests[-1]["tools"] == baseline_tools
        summary.update({"passed": True, "physical_requests": len(requests),
                        "skill_sections": 1, "style_followed": True, "user_priority_followed": True,
                        "exact_user_output_matched": exact_user_output,
                        "tool_catalog_unchanged": True,
                        "system_prompt_sha256": sha256(system.encode()).hexdigest(),
                        "effective_context": backend.context_length,
                        "effective_output_reserve": backend.max_response_tokens})
    finally:
        service.shutdown()
        exited = process is None or process.poll() is not None
        summary["owned_server_exited"] = exited
        JsonStore(PATHS.state / "test-artifacts/skill-phase3-1-live.json").save(summary)
        assert exited
