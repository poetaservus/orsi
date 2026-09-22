from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.execution.audit import CallLifecycleState
from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
from app.settings.agent import AgentFeatureConfig
from app.settings.cloud import CloudConfig, load_cloud_config


_LIVE_CLOUD_ENABLED = os.environ.get("ORSI_RUN_LIVE_CLOUD_MODEL_ACCEPTANCE") == "1"
_LIVE_CLOUD_KEY_PRESENT = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
_CONFIGURED_MODELS = load_cloud_config().model_pool


@pytest.mark.skipif(
    not (_LIVE_CLOUD_ENABLED and _LIVE_CLOUD_KEY_PRESENT),
    reason=(
        "Set ORSI_RUN_LIVE_CLOUD_MODEL_ACCEPTANCE=1 and OPENROUTER_API_KEY "
        "to re-certify the configured free-model pool."
    ),
)
@pytest.mark.parametrize("model_id", _CONFIGURED_MODELS)
def test_configured_cloud_model_completes_tool_round_trip_and_no_tool_chat(
    tmp_path: Path,
    model_id: str,
):
    """Opt-in gate: every pool member must work alone without failover masking it."""
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    probe = portable_root / "cloud-model-probe.txt"
    probe.write_bytes(b"cloud model acceptance")
    state = tmp_path / "state"
    base = load_cloud_config()
    single_model = CloudConfig.model_validate(
        {
            **base.model_dump(mode="python"),
            "model": model_id,
            "fallback_models": (),
        }
    )
    model = OpenAICompatibleInferenceEngine(single_model)
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True),
        portable_root=portable_root,
        state_directory=state,
    )
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    try:
        answer = service.run(
            "Use filesystem.stat exactly once to inspect cloud-model-probe.txt, "
            "then report its size in bytes."
        )

        records = runtime.executor.journal.records
        assert len(records) == 1, (model_id, answer, records)
        assert records[0].capability == "filesystem.stat"
        assert records[0].state == CallLifecycleState.COMPLETED
        assert str(probe.stat().st_size) in answer

        service.new_session()
        chat = service.run("Reply exactly with pool-chat-ok and do not use a tool.")
        assert "pool-chat-ok" in chat.casefold()
        assert runtime.executor.journal.records == ()
    finally:
        service.shutdown()
