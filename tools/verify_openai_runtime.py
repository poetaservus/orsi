"""Offline verification of the shipped SDK and portable cloud startup."""
from __future__ import annotations

import asyncio
import argparse
import json
from pathlib import Path


def verify(root: Path, *, cloud_only: bool = False) -> dict:
    import openai
    import httpx
    import PySide6
    from app.inference.openai_backend import OpenAIResponsesInferenceEngine, normalize_text_response
    from app.settings.openai_cloud import OpenAICloudConfig
    import tomllib
    manifest = tomllib.loads((root / "pyproject.toml").read_text())
    pin = next(value.split("==", 1)[1] for value in manifest["project"]["dependencies"] if value.startswith("openai=="))
    assert openai.__version__ == pin
    assert f"openai=={pin}" in (root / "requirements.txt").read_text().splitlines()
    config = OpenAICloudConfig.model_validate(json.loads((root / "config/cloud.json").read_text()))
    payload = {"id": "resp_fixture", "object": "response", "created_at": 0,
        "model": config.default_model, "status": "completed", "output": [{"type": "message",
        "id": "msg_fixture", "role": "assistant", "status": "completed", "content": [
        {"type": "output_text", "text": "OK", "annotations": []}]}],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
    async def check():
        async def reply(request):
            return httpx.Response(200, json=payload)
        async with openai.AsyncOpenAI(api_key="offline-fixture", base_url=config.base_url,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(reply))) as client:
            result = await client.responses.create(model=config.default_model, input="fixture", store=False)
            assert str(normalize_text_response(result.model_dump())) == "OK"
            assert callable(client.responses.input_tokens.count)
        assert client.is_closed()
    asyncio.run(check())
    engine = OpenAIResponsesInferenceEngine(config, api_key="")
    assert engine._client is None and not engine.has_api_key
    engine.close()
    report = {"passed": True, "sdk_version": openai.__version__, "qt_version": PySide6.__version__,
            "sdk_transport_fixture_passed": True, "lazy_client_released": True}
    if cloud_only:
        import logging
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.settings.paths import PATHS
        from app.runtime.skills import SkillRegistry
        from app.startup import build_application
        from app.ui.main_window import MainWindow
        assert PATHS.root.resolve() == root.resolve()
        assert not (root / "runtime/llama-server/llama-server.exe").exists()
        assert not list((root / "models").glob("*.gguf"))
        PATHS.ensure_directories()
        logging.disable(logging.CRITICAL)
        app = QApplication.instance() or QApplication([])
        service, _, error, inference = build_application(skill_registry_override=SkillRegistry(global_root=root / "state/fixture-skills"))
        try:
            assert service is not None and error is None and inference.local is None and inference.mode == "cloud"
            assert {"filesystem.stat", "filesystem.read_text", "filesystem.edit_text"} <= set(service.agent_capabilities)
            assert inference.cloud._client is None
            window = MainWindow(service, "package fixture", inference=inference)
            window.show()
            app.processEvents()
            window.close()
            app.processEvents()
            report.update(cloud_native_tools_startup=True, ui_startup_passed=True)
        finally:
            if service is not None:
                service.shutdown()
            inference.close()
            logging.disable(logging.NOTSET)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud-only", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(Path.cwd(), cloud_only=args.cloud_only)))
    except Exception as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__}))
        raise SystemExit(1)
