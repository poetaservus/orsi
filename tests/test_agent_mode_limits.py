"""Cloud/local step budgets follow the active backend without a live request."""
import logging

import pytest
from pydantic import ValidationError

from app.agent.contracts import AgentRunStatus
from app.inference.hybrid import HybridInferenceEngine
from app.inference.protocol import ModelResponse
from app.settings.agent import AgentRuntimeLimits, MAX_AGENT_STEPS, load_agent_feature_config
from tests.test_phase8_filesystem_stat import ScriptedStatModel, build_service, stat_call


def scripted_model(call_count):
    model = ScriptedStatModel([stat_call(f"fixture-{index}.txt", provider_call_id=f"stat-{index}")
        for index in range(call_count)] + [ModelResponse.text("Done")])
    model.context_length = 131_072
    model.max_response_tokens = 512
    return model


def test_accepted_configuration_and_legacy_settings_keep_local_24_and_maximum_cloud_32():
    settings = load_agent_feature_config().runtime_limits
    assert settings.max_steps == 24
    assert settings.cloud_max_steps == MAX_AGENT_STEPS == 32
    assert AgentRuntimeLimits.model_validate({"max_steps": 24}).cloud_max_steps == 32
    with pytest.raises(ValidationError):
        AgentRuntimeLimits(cloud_max_steps=MAX_AGENT_STEPS + 1)


def test_real_switch_cloud_local_cloud_applies_budgets_and_retains_history(tmp_path, caplog):
    cloud, local = scripted_model(31), scripted_model(24)
    hybrid = HybridInferenceEngine(local=local, cloud=cloud, default_mode="cloud", fallback_to_local=False)
    service, runtime, store, root = build_service(tmp_path, hybrid)
    caplog.set_level(logging.INFO, logger="app.agent.runtime")
    try:
        assert runtime.limits.max_steps == 24 and runtime.effective_max_steps == 32
        assert service.run("Inspect the synthetic fixtures") == "Done"
        outcome = store._conversation.turns[-1].outcome
        assert outcome.status == AgentRunStatus.COMPLETED and outcome.steps == 32
        assert outcome.capability_calls == 31 and len(cloud.requests) == 32
        history = store.messages()
        hybrid.set_mode("local")
        assert runtime.effective_max_steps == 24 and store.messages() == history
        with pytest.raises(RuntimeError, match="maximum model-step limit"):
            service.run("Inspect the synthetic fixtures again")
        outcome = store._conversation.turns[-1].outcome
        assert outcome.status == AgentRunStatus.STEP_LIMIT and outcome.steps == 24
        assert outcome.capability_calls == 24 and len(local.requests) == 24
        history = store.messages()
        cloud.responses = scripted_model(31).responses
        hybrid.set_mode("cloud")
        assert runtime.effective_max_steps == 32 and store.messages() == history
        assert service.run("Inspect the synthetic fixtures once more") == "Done"
        assert store._conversation.turns[-1].outcome.steps == 32
        assert "mode=cloud max_steps=32" in caplog.text and "mode=local max_steps=24" in caplog.text
        reopened = type(store)(store.path)
        assert [turn.outcome.steps for turn in reopened._conversation.turns] == [32, 24, 32]
    finally:
        service.shutdown()


def test_cloud_stops_at_32_without_sending_request_33(tmp_path):
    cloud = scripted_model(32)
    hybrid = HybridInferenceEngine(local=None, cloud=cloud, default_mode="cloud", fallback_to_local=False)
    service, runtime, store, root = build_service(tmp_path, hybrid)
    try:
        with pytest.raises(RuntimeError, match="maximum model-step limit"):
            service.run("Inspect the synthetic fixtures")
        outcome = store._conversation.turns[-1].outcome
        assert outcome.steps == outcome.model_requests == outcome.capability_calls == 32
        assert len(cloud.requests) == 32 and len(cloud.responses) == 1
        assert len(store._conversation.turns[-1].settled_calls) == 32
    finally:
        service.shutdown()


@pytest.mark.parametrize("backend", ["responses", "compatible"])
def test_direct_cloud_adapters_use_cloud_budget_without_a_hybrid(tmp_path, backend):
    if backend == "responses":
        from app.inference.openai_backend import OpenAIResponsesInferenceEngine
        from tests.test_openai_phase1 import config
        engine = OpenAIResponsesInferenceEngine(config(), api_key="fake-never-live")
    else:
        from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
        from tests.test_cloud_inference import cloud_config
        engine = OpenAICompatibleInferenceEngine(cloud_config(), api_key="fake-never-live")
    service, runtime, store, root = build_service(tmp_path, engine)
    try:
        assert runtime.effective_max_steps == 32 and runtime.limits.max_steps == 24
    finally:
        service.shutdown()
