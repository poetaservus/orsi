"""Opt-in native vision qualification; synthetic sources, isolated selection, numeric diagnostics."""
import base64
import json
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter, QColor

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.hybrid import HybridInferenceEngine, LazyInferenceEngine
from app.inference.llama_server_backend import LlamaServerInferenceEngine
from app.security.host_access import HostAccessPolicy
from app.settings.agent import load_agent_feature_config
from app.settings.local_models import LocalModelCatalog
from app.settings.model import load_model_config, detect_nvidia_memory_mib
from app.settings.paths import PATHS


pytestmark = pytest.mark.skipif(os.environ.get("ORSI_RUN_IMAGE_INPUT_LIVE") != "1",
                               reason="Opt-in native vision model/projector qualification")


def visual(format="PNG", *, reverse=False):
    image = QImage(640, 320, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.fillRect(20, 20, 280, 280, QColor("blue" if reverse else "red"))
    painter.fillRect(340, 20, 280, 280, QColor("red" if reverse else "blue"))
    painter.end()
    output = QBuffer();output.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(output, format)
    return bytes(output.data())


def test_native_visual_formats_followups_archive_tools_and_real_switch(tmp_path):
    if os.name != "nt":
        pytest.skip("Native Windows vision qualification")
    processes = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if '"llama-server.exe"' in processes.stdout.lower():
        pytest.skip("An existing model server belongs to another session")
    if detect_nvidia_memory_mib() is None:
        pytest.skip("GPU vision gate; CPU loading remains separately unqualified")
    before = (PATHS.config / "model.json").read_bytes()
    selection = PATHS.state / "local_model_selection_v1.json"
    selected_before = selection.read_bytes() if selection.exists() else None
    catalog = LocalModelCatalog(PATHS.models, PATHS.config / "model.json", load_model_config(),
        selection_path=tmp_path / "selection.json")
    text_id, vision_id = "Qwen314BQ4KM.gguf", "Qwen3VL4BInstructQ4KM.gguf"
    initial = catalog.configuration(text_id);catalog.current_config = initial
    physical, switches, owned = [], [], []
    def factory(config):
        engine = LlamaServerInferenceEngine(config)
        actual = engine._request_completion
        def audit(payload):
            result = actual(payload);usage = result.get("usage", {})
            physical.append({"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                "tool_count": len(payload.get("tools", [])), "finish_reason": result["choices"][0].get("finish_reason")})
            return result
        engine._request_completion = audit
        return engine
    lazy = LazyInferenceEngine(lambda: factory(catalog.configuration(text_id)), context_length=initial.context_length,
        max_response_tokens=initial.max_tokens, supports_local_document_inputs=True)
    inference = HybridInferenceEngine(local=lazy, cloud=None, model_catalog=catalog, local_factory=factory)
    plain = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
    runtime = None;passed = False
    def record():
        engine = inference.local._get_engine();engine.prepare()
        url,key,process = engine._ensure_started();owned.append(process)
        with urlopen(Request(url + "/props", headers={"Authorization": "Bearer " + key}), timeout=10) as reply:
            props = json.load(reply)
        actual_ctx = props["default_generation_settings"]["n_ctx"]
        assert actual_ctx == engine.context_length == inference.context_length == 16384
        assert engine.max_response_tokens == inference.max_response_tokens == 4096
        resolution = catalog.diagnostic();memory = detect_nvidia_memory_mib()
        allocated = resolution["gpu_before_load_mib"]["free"] - memory[1]
        assert memory[1] >= memory[0] * .2 and allocated <= resolution["estimated_allocation_mib"]
        switches.append({"model_id": catalog.current_id,"actual_context":actual_ctx,"output_reserve":engine.max_response_tokens,
            "sampling":engine.config.sampling_parameters(),"gpu_layers":engine.config.gpu_layers,
            "observed_allocation_mib":allocated,"estimated_allocation_mib":resolution["estimated_allocation_mib"],
            "vision":resolution.get("vision")})
    try:
        record()
        assert not inference.supports_local_image_inputs
        inference.select_local_model(vision_id)
        assert owned[-1].poll() is not None
        record();assert inference.supports_local_image_inputs
        first = plain.store.attachment_store.import_bytes(visual(), name="first.png")
        answer = plain.run("Describe the shapes and their colours from left to right.", attachments=[first])
        words = answer.casefold();assert "red" in words and "blue" in words and words.index("red") < words.index("blue")
        second = plain.store.attachment_store.import_bytes(visual("JPEG", reverse=True), name="second.jpg")
        answer = plain.run("Describe the shapes and their colours from left to right in the new image.", attachments=[second])
        words = answer.casefold();assert "red" in words and "blue" in words and words.index("blue") < words.index("red")
        answer = plain.run("What colour was on the left in the first image? Reply with just the colour.")
        assert "red" in answer.casefold()
        restored = ConversationService(inference, ConversationStore(tmp_path / "chat.json"))
        answer = restored.run("What colour was on the left in the second image? Reply with just the colour.")
        assert "blue" in answer.casefold()
        restored.store.new_session(preserve_history=True)
        archive = next((tmp_path / "archives").glob("*.json"))
        archived = ConversationService(inference, ConversationStore(archive))
        answer = archived.run("What colour was on the left in the first image? Reply with just the colour.")
        assert "red" in answer.casefold()
        plain.new_session()
        webp = plain.store.attachment_store.import_bytes(visual("WEBP"), name="third.webp")
        answer = plain.run("Describe the shapes and their colours from left to right.", attachments=[webp])
        words=answer.casefold();assert "red" in words and "blue" in words
        plain.new_session()
        # Still GIF is validated by Qt and transported as a lossless PNG.
        gif=plain.store.attachment_store.import_bytes(base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"),name="still.gif")
        assert plain.run("Describe this image.",attachments=[gif]).strip()
        portable=tmp_path/'portable';portable.mkdir();(portable/'fixture.txt').write_text('synthetic fixture')
        flags=load_agent_feature_config()
        policy=(HostAccessPolicy.full_local(application_root=portable,user_home=portable,acknowledged=True)
                if flags.full_local_read_enabled else HostAccessPolicy.portable_root(portable))
        runtime=build_agent_runtime(inference,config=flags,portable_root=portable,
            state_directory=portable/'state',host_access_policy=policy)
        agent=ConversationService(inference,ConversationStore(portable/'chat.json'),agent_runtime=runtime,
            portable_root=portable,host_access_policy=policy)
        agent.set_approval_requester(lambda r:agent.resolve_approval(r.approval_id,False))
        attached=agent.store.attachment_store.import_bytes(visual(),name='stat-image.png')
        answer=agent.run("Check fixture.txt with filesystem.stat, then describe the colours from left to right in the attached image.",attachments=[attached])
        assert "red" in answer.casefold() and "blue" in answer.casefold()
        assert any(c.call.capability=='filesystem.stat' for c in agent.store.turns()[0].settled_calls)
        assert agent.context_budget().fits and agent.active_skill is None
        previous=owned[-1]
        inference.select_local_model(text_id);assert previous.poll() is not None
        record();assert not inference.supports_local_image_inputs
        assert plain.inference.respond([{"role":"user","content":"Reply with OK only."}]).strip()
        assert switches[0]['sampling']==switches[-1]['sampling']
        assert all(p['finish_reason'] in {'stop','tool_calls'} for p in physical)
        passed=True
    finally:
        inference.close()
        if runtime is not None:runtime.shutdown()
        released=all(p.poll() is not None for p in owned)
        unchanged=(PATHS.config/'model.json').read_bytes()==before and (selection.read_bytes() if selection.exists() else None)==selected_before
        summary={'scope':'local_image_input_phase3b','passed':passed,'switches':switches,'physical_requests':physical,
            'owned_processes_released':released,'user_selection_and_profiles_unchanged':unchanged}
        (tmp_path/'live-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
        assert released and unchanged


def test_native_cpu_vision_fallback_actual_limits_and_release(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Native Windows CPU vision qualification")
    processes = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if '"llama-server.exe"' in processes.stdout.lower():
        pytest.skip("Another session owns a model server")
    before=(PATHS.config/'model.json').read_bytes()
    monkeypatch.setattr('app.settings.local_models.detect_nvidia_memory_mib',lambda:None)
    catalog=LocalModelCatalog(PATHS.models,PATHS.config/'model.json',load_model_config(),selection_path=tmp_path/'selection.json')
    cfg=catalog.configuration('Qwen3VL4BInstructQ4KM.gguf')
    assert cfg.context_length==4096 and cfg.max_tokens==1024 and cfg.gpu_layers==0
    engine=LlamaServerInferenceEngine(cfg);owned=None;passed=False
    app=ConversationService(engine,ConversationStore(tmp_path/'chat.json'))
    try:
        engine.prepare();url,key,owned=engine._ensure_started()
        with urlopen(Request(url+'/props',headers={'Authorization':'Bearer '+key}),timeout=10) as reply:
            props=json.load(reply)
        assert props['default_generation_settings']['n_ctx']==4096
        ref=app.store.attachment_store.import_bytes(visual(),name='cpu.png')
        answer=app.run('Describe the shapes and their colours from left to right.',attachments=[ref])
        words=answer.casefold();assert 'red' in words and 'blue' in words and words.index('red')<words.index('blue')
        assert app.context_budget().fits
        passed=True
    finally:
        engine.close();released=owned is None or owned.poll() is not None
        summary={'scope':'local_image_input_phase3b_cpu','passed':passed,'context_length':engine.context_length,
            'output_reserve':engine.max_response_tokens,'gpu_layers':cfg.gpu_layers,'owned_process_released':released,
            'profiles_unchanged':(PATHS.config/'model.json').read_bytes()==before}
        (tmp_path/'live-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
        assert released and summary['profiles_unchanged']
