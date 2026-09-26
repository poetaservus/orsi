from __future__ import annotations

import os

import pytest

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.security.host_access import HostAccessPolicy
from app.settings.agent import AgentFeatureConfig
from app.settings.model import load_model_config
from tests.fixtures.context_reliability import large_css_fixture


@pytest.mark.skipif(os.name != "nt" or os.environ.get("ORSI_RUN_LIVE_EDIT_TEXT") != "1",
                    reason="Set ORSI_RUN_LIVE_EDIT_TEXT=1 for local Qwen edit acceptance.")
def test_local_model_reads_and_edits_large_css(tmp_path):
    portable = tmp_path / "portable"
    portable.mkdir()
    target = tmp_path / "styles.css"
    original = large_css_fixture().encode()
    target.write_bytes(original)
    model = LlamaServerInferenceEngine(load_model_config())
    policy = HostAccessPolicy.full_local(application_root=portable, user_home=tmp_path,
                                         acknowledged=True)
    runtime = build_agent_runtime(model,
        config=AgentFeatureConfig(filesystem_stat_enabled=True, filesystem_read_text_enabled=True,
                                  filesystem_edit_text_enabled=True, full_local_read_enabled=True),
        portable_root=portable, state_directory=portable / "state", host_access_policy=policy)
    service = ConversationService(model, ConversationStore(portable / "conversation.json"),
                                   agent_runtime=runtime, portable_root=portable,
                                   host_access_policy=policy)
    previews = []
    def approve(record):
        assert record.capability == "filesystem.edit_text"
        assert record.resource == str(target)
        assert target.read_bytes() == original
        previews.append(record.approval_preview)
        service.resolve_approval(record.approval_id, True)
    service.set_approval_requester(approve)
    try:
        service.run(
            f'Edit "{target}": change only the color of .phase0-component-001 from '
            '#123456 to #ffffff. First use filesystem.read_text with max_bytes=1024 and '
            'max_lines=1, then filesystem.edit_text with a unique short exact excerpt. '
            'Preserve all other bytes. Do not return or replace the entire file.'
        )
        assert target.read_bytes() == original.replace(b"#123456", b"#ffffff", 1)
        records = runtime.executor.journal.records
        assert any(r.capability == "filesystem.read_text" and r.result_success for r in records)
        assert sum(r.capability == "filesystem.edit_text" and r.result_success for r in records) == 1
        assert len(previews) == 1 and len(previews[0]) < 3000
    finally:
        service.shutdown()
        model.close()
