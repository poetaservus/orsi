"""Shipped local/cloud modes use only the skill deliberately attached to a turn."""
import os
from types import SimpleNamespace

import pytest

from app.inference.hybrid import HybridInferenceEngine
from app.runtime.skills import SkillRegistry
from app.settings.agent import AgentFeatureConfig
from app.settings.paths import RuntimePaths
from tests.test_skill_activation import make_service, skill_payload, write_skill
from tests.test_skill_selection import Recorder


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows skill loading")


@pytest.mark.parametrize("mode", ["local", "cloud"])
@pytest.mark.parametrize("agent", [False, True])
@pytest.mark.parametrize("switch_mode", [False, True])
def test_default_never_routes_follow_ups_but_preserves_history_and_explicit_attachment(
    tmp_path, mode, agent, switch_mode
):
    # These backends would choose an installed skill if a router request reached them.
    local = Recorder(['{"skill": "style"}'] * 3)
    cloud = Recorder(['{"skill": "style"}'] * 3)
    inference = HybridInferenceEngine(local=local, cloud=cloud, default_mode=mode,
                                      fallback_to_local=False)
    service, _ = make_service(tmp_path, model=inference, agent=agent)
    names, activities = [], []
    initial = "Write a Python media player."
    selected = "Refine this Python media player."
    follow_up = "SyntaxError: unterminated string literal at line 232. Please fix it."
    try:
        assert service.automatic_skills_enabled is False
        assert service.skill_registry.get("style") is not None
        assert service.run(initial, skill_observer=names.append, activity=activities.append) == "reply"
        first_backend = local if mode == "local" else cloud
        first_messages, first_tools = first_backend.answer_requests[-1]
        assert "\nACTIVE SKILL\n" not in first_messages[0]["content"]
        assert service.skill_selection.reason == "disabled"
        assert service.run(selected, skill_name="style", skill_observer=names.append) == "reply"
        assert skill_payload(first_backend.answer_requests[-1][0])["name"] == "style"
        assert service.active_skill is None
        if switch_mode:
            inference.set_mode("cloud" if mode == "local" else "local")
        assert service.run(follow_up, skill_observer=names.append, activity=activities.append) == "reply"
        last_backend = local if inference.mode == "local" else cloud
        messages, tools = last_backend.answer_requests[-1]
        assert "\nACTIVE SKILL\n" not in messages[0]["content"]
        assert messages[1:] == [
            {"role": "user", "content": initial},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": selected},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": follow_up},
        ]
        assert tools == first_tools
        assert not local.router_requests and not cloud.router_requests
        assert len(local.answer_requests) + len(cloud.answer_requests) == 3
        assert names == ["style"]
        assert "Choosing a skill…" not in activities
        assert [m.skill_name for m in service.store.visible_messages() if m.role == "user"] == [None, "style", None]
        assert service.active_skill is None and service.skill_selection.reason == "disabled"
    finally:
        service.shutdown()


@pytest.mark.parametrize("mode", ["local", "cloud"])
def test_application_startup_explicitly_disables_automatic_skills(tmp_path, monkeypatch, mode):
    import app.startup as startup

    paths = RuntimePaths(tmp_path, tmp_path / "config", tmp_path / "models", tmp_path / "state")
    paths.ensure_directories()
    model_path = paths.models / "fixture.gguf"
    model_path.touch()
    local, cloud = Recorder(['{"skill": "style"}']), Recorder(['{"skill": "style"}'])
    monkeypatch.setattr(startup, "PATHS", paths)
    monkeypatch.setattr(startup, "load_cloud_config", lambda: SimpleNamespace(
        default_mode=mode, fallback_to_local=False))
    monkeypatch.setattr(startup, "OpenAICompatibleInferenceEngine", lambda _: cloud)
    monkeypatch.setattr(startup, "load_model_config", lambda: SimpleNamespace(
        resolved_model_path=model_path, maximum_context_length=16384, max_tokens=128,
        select_context=lambda **kwargs: SimpleNamespace(length=16384)))
    monkeypatch.setattr(startup, "LocalModelCatalog", lambda *args: SimpleNamespace(
        profiles=None, models=[], current_id="fixture.gguf"))
    monkeypatch.setattr(startup, "detect_nvidia_memory_mib", lambda: None)
    monkeypatch.setattr(startup, "LlamaCppInferenceEngine", lambda _: local)
    observed = []
    original_service = startup.ConversationService

    def build_service(*args, **kwargs):
        observed.append(kwargs.get("automatic_skills_enabled"))
        return original_service(*args, **kwargs)

    monkeypatch.setattr(startup, "ConversationService", build_service)
    root = tmp_path / "skills"
    write_skill(root, "style")
    service, _, error, inference = startup.build_application(
        agent_config_override=AgentFeatureConfig(),
        skill_registry_override=SkillRegistry(global_root=root))
    try:
        assert error is None and service is not None and inference.mode == mode
        assert observed == [False] and service.automatic_skills_enabled is False
        assert service.run("Write a Python media player.") == "reply"
        assert service.skill_selection.reason == "disabled"
        assert not local.router_requests and not cloud.router_requests
        backend = local if mode == "local" else cloud
        assert len(backend.answer_requests) == 1
        assert "\nACTIVE SKILL\n" not in backend.answer_requests[0][0][0]["content"]
    finally:
        if service is not None:
            service.shutdown()
