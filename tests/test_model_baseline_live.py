"""Opt-in, content-free evidence against the actual shipped GGUFs and GPU."""
import json
import os
from pathlib import Path
from time import monotonic
from urllib.request import Request, urlopen

import pytest

from app.infrastructure.baseline import BaselineRecorder
from app.agent.bootstrap import build_agent_runtime
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import detect_nvidia_memory_mib, load_model_config
from app.settings.paths import PATHS
from app.security.host_access import HostAccessPolicy
from app.state.storage import JsonStore


pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("ORSI_RUN_MODEL_BASELINE") != "1",
    reason="Opt-in real model baseline and switch acceptance",
)


def test_14b_small_model_14b_restores_baseline_and_releases_gpu(tmp_path):
    manifest_before = (PATHS.config / "model.json").read_bytes()
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
                                selection_path=tmp_path / "selection.json")
    initial_id = "Qwen314BQ4KM.gguf"
    initial = catalog.configuration(initial_id)
    catalog.current_config = initial
    local = LazyInferenceEngine(
        lambda: LlamaServerInferenceEngine(catalog.configuration(initial_id)),
        context_length=initial.context_length, max_response_tokens=initial.max_tokens)
    inference = HybridInferenceEngine(local=local, cloud=None, model_catalog=catalog,
                                      local_factory=LlamaServerInferenceEngine)
    # Match a launch before the optional full-local read acknowledgement.
    flags = load_agent_feature_config().model_copy(update={"full_local_read_enabled": False})
    snapshot = tmp_path / "baseline.json"
    inference.baseline_observer = BaselineRecorder(PATHS.root, snapshot, flags, agent_available=True)
    processes, records = [], []
    runtime = None
    started = monotonic()
    try:
        runtime = build_agent_runtime(inference, config=flags, portable_root=PATHS.root,
            state_directory=tmp_path / "agent", host_access_policy=HostAccessPolicy.portable_root(PATHS.root))
        assert runtime is not None and runtime.registry.model_visible_names
        for model_id in (initial_id, "model.gguf", initial_id):
            if catalog.current_id != model_id:
                previous = processes[-1]
                inference.select_local_model(model_id)
                assert previous.poll() is not None, "The replaced server must exit before the next model loads"
            backend = inference.local._get_engine()
            backend.prepare()
            base_url, api_key, process = backend._ensure_started()
            processes.append(process)
            # Check the running server's context, rather than only the Python configuration.
            request = Request(base_url + "/props", headers={"Authorization": "Bearer " + api_key})
            with urlopen(request, timeout=10) as response:
                props = json.load(response)
            runtime_context = props["default_generation_settings"]["n_ctx"]
            assert runtime_context == backend.context_length == 16384
            assert backend.max_response_tokens == 4096
            assert inference.respond([{"role": "user", "content": "Reply with OK only."}]).strip()
            inference.record_baseline()
            record = json.loads(snapshot.read_text())
            assert record["local_model"]["model_id"] == model_id
            assert record["active_limits"] == {"context_length": 16384, "max_response_tokens": 4096}
            memory = record["gpu_at_capture_mib"]
            assert memory and memory["free"] >= memory["total"] * 0.2, "Retain 20% total VRAM headroom after an actual load"
            model = record["local_model"]
            actual_allocation = model["gpu_before_load_mib"]["free"] - memory["free"]
            assert actual_allocation <= model["estimated_allocation_mib"], "The guard must cover the observed allocation"
            record["observed_allocation_mib"] = actual_allocation
            record["verified_runtime_context"] = runtime_context
            record["owned_server_pid"] = process.pid
            records.append(record)
            print(model_id, "context=16384 output=4096", "GPU free MiB=", memory["free"], flush=True)
        assert records[0]["local_model"]["sha256"] == records[-1]["local_model"]["sha256"]
        assert records[0]["local_model"]["effective"] == records[-1]["local_model"]["effective"]
        assert (PATHS.config / "model.json").read_bytes() == manifest_before
        assert catalog.selected_id() == initial_id
    finally:
        inference.close()
        if runtime is not None:
            runtime.shutdown()
        assert all(process.poll() is not None for process in processes)
    JsonStore(PATHS.state / "test-artifacts/model-baseline-live.json").save({
        "schema_version": 1, "passed": True, "duration_seconds": round(monotonic() - started, 2),
        "switches": records, "all_owned_servers_exited": True,
        "gpu_after_shutdown_mib": detect_nvidia_memory_mib(),
    })
