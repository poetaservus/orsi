from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.agent_bootstrap import build_filesystem_stat_runtime
from app.agent_config import AgentFeatureConfig
from app.capabilities.crash_journal import CallLifecycleState
from app.conversation.service import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_backend import LlamaCppInferenceEngine
from app.inference.model_config import load_model_config


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_MODEL_TESTS") != "1",
    reason="Set ORSI_RUN_LIVE_MODEL_TESTS=1 for the bundled-model smoke test.",
)
def test_bundled_model_completes_a_filesystem_stat_round_trip(tmp_path: Path):
    """Opt-in smoke test: no scripted provider responses participate in this path."""
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    probe = portable_root / "phase8-live-probe.txt"
    probe.write_text("metadata-only live smoke", encoding="utf-8")
    state = tmp_path / "state"
    model = LlamaCppInferenceEngine(load_model_config())
    runtime = build_filesystem_stat_runtime(
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
            "Use filesystem.stat to inspect phase8-live-probe.txt, then tell me its size."
        )

        assert answer.strip()
        records = runtime.executor.journal.records
        assert len(records) == 1, f"Bundled model answer without a stat record: {answer}"
        assert records[0].state == CallLifecycleState.COMPLETED
    finally:
        service.shutdown()
        model.close()
