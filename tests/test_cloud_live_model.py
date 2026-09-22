from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.agent.runtime import AgentRuntime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.execution.audit import CallLifecycleState
from app.inference.cloud_backend import OpenAICompatibleInferenceEngine
from app.settings.agent import AgentFeatureConfig
from app.settings.cloud import CloudConfig, load_cloud_config


_LIVE_CLOUD_ENABLED = os.environ.get("ORSI_RUN_LIVE_CLOUD_MODEL_ACCEPTANCE") == "1"
_LIVE_CLOUD_KEY_PRESENT = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
_CONFIGURED_MODELS = load_cloud_config().model_pool
_WRITE_CAPABILITIES = frozenset(
    {
        "filesystem.copy",
        "filesystem.mkdir",
        "filesystem.move",
        "filesystem.trash",
        "filesystem.write_text",
    }
)
_LIVE_CLOUD_MARK = pytest.mark.skipif(
    not (_LIVE_CLOUD_ENABLED and _LIVE_CLOUD_KEY_PRESENT),
    reason=(
        "Set ORSI_RUN_LIVE_CLOUD_MODEL_ACCEPTANCE=1 and OPENROUTER_API_KEY "
        "to re-certify the configured free-model pool."
    ),
)
_CAPABILITY_CASES = (
    pytest.param("listing", "filesystem.list", "filesystem_list_enabled", id="listing"),
    pytest.param(
        "reading",
        "filesystem.read_text",
        "filesystem_read_text_enabled",
        id="reading",
    ),
    pytest.param(
        "multiline-writing",
        "filesystem.write_text",
        "filesystem_write_text_enabled",
        id="multiline-writing",
    ),
    pytest.param(
        "searching",
        "filesystem.search",
        "filesystem_search_enabled",
        id="searching",
    ),
    pytest.param("copying", "filesystem.copy", "filesystem_copy_enabled", id="copying"),
    pytest.param("moving", "filesystem.move", "filesystem_move_enabled", id="moving"),
    pytest.param(
        "folder-creation",
        "filesystem.mkdir",
        "filesystem_mkdir_enabled",
        id="folder-creation",
    ),
    pytest.param(
        "trashing",
        "filesystem.trash",
        "filesystem_trash_enabled",
        id="trashing",
    ),
)


def _single_model_config(model_id: str) -> CloudConfig:
    base = load_cloud_config()
    return CloudConfig.model_validate(
        {
            **base.model_dump(mode="python"),
            "model": model_id,
            "fallback_models": (),
        }
    )


def _build_live_service(
    tmp_path: Path,
    model_id: str,
    *,
    feature_flag: str | None = None,
) -> tuple[ConversationService, AgentRuntime, Path]:
    portable_root = tmp_path / "portable"
    portable_root.mkdir()
    state = tmp_path / "state"
    model = OpenAICompatibleInferenceEngine(_single_model_config(model_id))
    feature_values = {"filesystem_stat_enabled": True}
    if feature_flag is not None:
        feature_values[feature_flag] = True
    runtime = build_agent_runtime(
        model,
        config=AgentFeatureConfig.model_validate(feature_values),
        portable_root=portable_root,
        state_directory=state,
    )
    assert runtime is not None
    service = ConversationService(
        model,
        ConversationStore(state / "conversation.json"),
        agent_runtime=runtime,
        portable_root=portable_root,
        allowed_read_roots=(portable_root,),
    )
    return service, runtime, portable_root


def _prepare_capability_case(
    case_name: str,
    portable_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, dict[str, Any]]:
    if case_name == "listing":
        marker = portable_root / "matrix-list-marker.txt"
        marker.write_text("listed", encoding="utf-8")
        return (
            f'Use filesystem.list exactly once to list "{portable_root}". '
            "Do not call another tool. Then repeat the exact filename matrix-list-marker.txt.",
            {"marker": marker.name},
        )

    if case_name == "reading":
        target = portable_root / "matrix-read.txt"
        sentinel = "READ-MATRIX-SENTINEL-7319"
        target.write_text(f"first line\n{sentinel}\nlast line", encoding="utf-8")
        return (
            f'Use filesystem.read_text exactly once to read "{target}". '
            "Do not call another tool. Then repeat the sentinel from the file.",
            {"sentinel": sentinel},
        )

    if case_name == "multiline-writing":
        target = portable_root / "matrix-written.txt"
        text = "matrix-line-one\nmatrix-line-two\nmatrix-line-three"
        return (
            f'Use filesystem.write_text exactly once to create "{target}" with exactly '
            "the following UTF-8 text, preserving the two newlines and adding no final newline:\n"
            f"{text}\nDo not call another tool.",
            {"target": target, "text": text},
        )

    if case_name == "searching":
        target = portable_root / "matrix-search-result.txt"
        sentinel = "SEARCH-MATRIX-SENTINEL-8426"
        target.write_text(f"ordinary text\n{sentinel} appears here\n", encoding="utf-8")
        return (
            f'Use filesystem.search exactly once to search "{portable_root}" for the literal '
            f'text "{sentinel}". Do not call another tool. Then report the matching filename '
            "and repeat the exact matched text.",
            {"filename": target.name, "sentinel": sentinel},
        )

    if case_name == "copying":
        source = portable_root / "matrix-copy-source.txt"
        destination = portable_root / "matrix-copy-destination.txt"
        text = "COPY-MATRIX-CONTENT-9537"
        source.write_text(text, encoding="utf-8")
        return (
            f'Use filesystem.copy exactly once to copy "{source}" to "{destination}" with '
            "collision policy fail. Do not call another tool.",
            {"source": source, "destination": destination, "text": text},
        )

    if case_name == "moving":
        source = portable_root / "matrix-move-source.txt"
        destination = portable_root / "matrix-move-destination.txt"
        text = "MOVE-MATRIX-CONTENT-1648"
        source.write_text(text, encoding="utf-8")
        return (
            f'Use filesystem.move exactly once to move "{source}" to "{destination}" with '
            "collision policy fail. Do not call another tool.",
            {"source": source, "destination": destination, "text": text},
        )

    if case_name == "folder-creation":
        target = portable_root / "matrix-created-folder"
        return (
            f'Use filesystem.mkdir exactly once to create "{target}". '
            "Do not call another tool.",
            {"target": target},
        )

    if case_name == "trashing":
        target = portable_root / "matrix-trash-target.txt"
        holding_directory = portable_root / ".live-matrix-trash"
        held_target = holding_directory / target.name
        text = "TRASH-MATRIX-CONTENT-2759"
        target.write_text(text, encoding="utf-8")
        holding_directory.mkdir()

        def hold_trashed_file(path: Path, cancellation) -> None:
            cancellation.raise_if_cancelled()
            path.replace(held_target)

        monkeypatch.setattr(
            "app.capabilities.filesystem_trash.trash_file",
            hold_trashed_file,
        )
        return (
            f'Use filesystem.trash exactly once to send "{target}" to the Recycle Bin. '
            "Do not call another tool.",
            {
                "target": target,
                "held_target": held_target,
                "text": text,
            },
        )

    raise AssertionError(f"Unknown live capability case: {case_name}")


def _verify_capability_case(
    case_name: str,
    expected: dict[str, Any],
    answer: str,
) -> None:
    if case_name == "listing":
        assert expected["marker"] in answer
        return
    if case_name == "reading":
        assert expected["sentinel"] in answer
        return
    if case_name == "multiline-writing":
        assert expected["target"].read_text(encoding="utf-8") == expected["text"]
        return
    if case_name == "searching":
        assert expected["filename"] in answer
        assert expected["sentinel"] in answer
        return
    if case_name == "copying":
        assert expected["source"].read_text(encoding="utf-8") == expected["text"]
        assert expected["destination"].read_text(encoding="utf-8") == expected["text"]
        return
    if case_name == "moving":
        assert not expected["source"].exists()
        assert expected["destination"].read_text(encoding="utf-8") == expected["text"]
        return
    if case_name == "folder-creation":
        assert expected["target"].is_dir()
        assert list(expected["target"].iterdir()) == []
        return
    if case_name == "trashing":
        assert not expected["target"].exists()
        assert expected["held_target"].read_text(encoding="utf-8") == expected["text"]
        return
    raise AssertionError(f"Unknown live capability case: {case_name}")


@_LIVE_CLOUD_MARK
@pytest.mark.parametrize("model_id", _CONFIGURED_MODELS)
@pytest.mark.parametrize(("case_name", "capability", "feature_flag"), _CAPABILITY_CASES)
def test_configured_cloud_model_completes_filesystem_matrix_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    case_name: str,
    capability: str,
    feature_flag: str,
):
    """Every pool member must complete every case alone, without failover masking it."""
    service, runtime, portable_root = _build_live_service(
        tmp_path,
        model_id,
        feature_flag=feature_flag,
    )
    prompt, expected = _prepare_capability_case(case_name, portable_root, monkeypatch)
    approvals = []

    def approve(record) -> None:
        assert record.capability == capability
        approvals.append(record)
        service.resolve_approval(record.approval_id, True)

    service.set_approval_requester(approve)
    try:
        answer = service.run(prompt)

        records = runtime.executor.journal.records
        assert len(records) == 1, (model_id, case_name, answer, records)
        assert records[0].capability == capability
        assert records[0].state == CallLifecycleState.COMPLETED
        assert records[0].result_success is True
        _verify_capability_case(case_name, expected, answer)

        if capability in _WRITE_CAPABILITIES:
            assert len(approvals) == 1
            assert service.approval_status(approvals[0].approval_id) == "consumed"
        else:
            assert approvals == []
    finally:
        service.shutdown()


@_LIVE_CLOUD_MARK
@pytest.mark.parametrize("model_id", _CONFIGURED_MODELS)
def test_configured_cloud_model_completes_stat_round_trip_and_no_tool_chat(
    tmp_path: Path,
    model_id: str,
):
    service, runtime, portable_root = _build_live_service(tmp_path, model_id)
    probe = portable_root / "cloud-model-probe.txt"
    probe.write_bytes(b"cloud model acceptance")
    try:
        answer = service.run(
            f'Use filesystem.stat exactly once to inspect "{probe}". '
            "Do not call another tool. Then report its size in bytes."
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
