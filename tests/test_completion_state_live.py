"""Opt-in actual provider length termination; never executes model tool requests."""
import os

import pytest

from app.inference.completion import IncompleteResponseError
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.inference.protocol import ModelCapabilityDefinition
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config
from app.settings.paths import PATHS
from app.state.storage import JsonStore


pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("ORSI_RUN_COMPLETION_STATE") != "1",
    reason="Opt-in actual model output-limit state acceptance",
)


def test_actual_length_termination_retains_metadata_and_cannot_authorize_calls(tmp_path):
    before = (PATHS.config / "model.json").read_bytes()
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=tmp_path / "selection.json")
    config = catalog.configuration("Qwen314BQ4KM.gguf")
    # Test-only physical request budget; the accepted profile stays at 4K.
    engine = LlamaServerInferenceEngine(config.model_copy(update={"max_tokens": 32}))
    observations = []
    process = None
    try:
        engine.prepare()
        process = engine._ensure_started()[2]
        try:
            response = engine.respond([{"role": "user", "content":
                "Provide a complete Python pygame top-down shooter with Player, Bullet, Enemy and Game classes. "
                "Return only the complete executable Python code block."}])
            completion = response.completion
            partial_chars = len(response)
        except IncompleteResponseError as exc:
            completion, partial_chars = exc.completion, len(exc.partial_text or "")
        assert completion.finish_reason == "length" and completion.incomplete
        assert completion.usage.output_tokens == 32
        observations.append({"request_kind": "text", "completion": completion.model_dump(),
                             "partial_text_chars": partial_chars})
        definition = ModelCapabilityDefinition(name="filesystem.write_text", description="Write one text file.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"},
                "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False})
        result = engine.respond_with_capabilities([{"role": "user", "content":
            "Use filesystem.write_text to create scratch.py with a complete Python pygame top-down shooter "
            "including Player, Bullet, Enemy and Game classes. Put the entire implementation in content."}], (definition,))
        assert result.completion.finish_reason == "length" and result.completion.incomplete
        assert not result.capability_calls
        observations.append({"request_kind": "tool", "completion": result.completion.model_dump(),
            "outcome": result.kind.value, "partial_text_chars": len(result.partial_text or result.assistant_text or ""),
            "executable_calls": len(result.capability_calls)})
        assert (PATHS.config / "model.json").read_bytes() == before
    finally:
        engine.close()
        assert process is None or process.poll() is not None
    JsonStore(PATHS.state / "test-artifacts/completion-state-live.json").save({
        "passed": True, "model_id": "Qwen314BQ4KM.gguf", "test_request_budget": 32,
        "profile_unchanged": True, "owned_server_exited": True, "observations": observations})
