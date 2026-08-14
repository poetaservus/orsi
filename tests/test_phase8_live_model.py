from __future__ import annotations

import os
from pathlib import Path
from threading import Thread

import pytest

from app.agent_bootstrap import build_filesystem_stat_runtime
from app.agent_config import AgentFeatureConfig
from app.capabilities.crash_journal import CallLifecycleState
from app.conversation.service import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
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
    model = LlamaServerInferenceEngine(load_model_config())
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


@pytest.mark.skipif(
    os.environ.get("ORSI_RUN_LIVE_MODEL_ACCEPTANCE") != "1",
    reason="Set ORSI_RUN_LIVE_MODEL_ACCEPTANCE=1 for the 25/25 model gate.",
)
def test_bundled_model_native_tool_call_acceptance_matrix(tmp_path: Path):
    """Real-model gate: native calls, no-call chat, failures, and cancellation."""
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside private body", encoding="utf-8")
    state = tmp_path / "state"
    model = LlamaServerInferenceEngine(load_model_config())
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
        for index in range(25):
            probe = portable_root / f"phase8-acceptance-{index}.txt"
            expected_size = 80 + index
            probe.write_bytes(bytes([65 + index % 26]) * expected_size)
            answer = service.run(
                "Use filesystem.stat exactly once to inspect "
                f"{probe.name}, then report its size in bytes."
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.COMPLETED
            assert str(expected_size) in answer
            service.new_session()

        for index in range(25):
            answer = service.run(
                f"This is ordinary conversation number {index}. "
                f"Reply exactly with chat-{index}; do not use a tool."
            )
            assert answer.strip()
            assert runtime.executor.journal.records == ()
            service.new_session()

        for index in range(5):
            answer = service.run(
                "Pass this exact path string to filesystem.stat once and let the "
                "capability decide whether it is allowed: "
                r"..\outside.txt"
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.DENIED
            service.new_session()

        for index in range(5):
            missing = f"missing-live-{index}.txt"
            answer = service.run(
                f"Use filesystem.stat exactly once to inspect {missing}."
            )
            records = runtime.executor.journal.records
            assert len(records) == 1, (index, answer, records)
            assert records[0].state == CallLifecycleState.FAILED
            service.new_session()

        for index in range(5):
            result: list[str] = []
            worker = Thread(
                target=lambda: result.append(
                    service.run(
                        "Write a detailed 1200-word essay about local inference "
                        f"for cancellation trial {index}. Do not use a tool."
                    )
                )
            )
            worker.start()
            assert model.wait_for_active_request(5.0)
            assert service.cancel_current_task()
            worker.join(5.0)
            assert not worker.is_alive()
            assert result == ["The response was stopped."]
            service.new_session()
    finally:
        service.shutdown()
        model.close()
