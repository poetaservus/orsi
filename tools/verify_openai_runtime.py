"""Offline verification of the shipped SDK, encrypted profiles and cloud startup."""
from __future__ import annotations

import asyncio
import argparse
import json
from pathlib import Path
import shutil
import tempfile


def verify_encrypted_profile(root: Path) -> dict:
    """Exercise real encryption in an owned fixture, never the selected profile."""
    import nacl
    import tomllib
    from app.vault import files
    from app.vault.profiles import ProfileManager
    from app.vault.types import Domain, State, VaultLocked

    manifest = tomllib.loads((root / "pyproject.toml").read_text())
    requirement = next(value for value in manifest["project"]["optional-dependencies"]["windows"]
                       if value.startswith("PyNaCl=="))
    pin = requirement.split("==", 1)[1]
    if nacl.__version__ != pin or requirement not in (root / "requirements.txt").read_text().splitlines():
        raise RuntimeError("Portable encryption dependency does not match the Windows manifest.")

    state = (root / "state").absolute()
    files.ordinary(state)
    state.mkdir(parents=True, exist_ok=True)
    state = state.resolve()
    fixture = Path(tempfile.mkdtemp(prefix="verify-vault-", dir=state))
    manager = None
    password = b"synthetic-package-verification-password"
    personal = b"synthetic-package-personal-record"
    credential = b"synthetic-package-credential-record"
    opened = []
    try:
        application = fixture / "application"
        application.mkdir()
        manager = ProfileManager(application)
        manager.create(application / "profiles" / "verification", mode="portable", password=password)
        vault = manager.vault()
        opened.append((vault, vault._keys))
        vault.put("verification/personal", personal)
        vault.put("verification/credential", credential, domain=Domain.CREDENTIAL)
        if (vault.read("verification/personal") != personal
                or vault.read("verification/credential", domain=Domain.CREDENTIAL) != credential):
            raise RuntimeError("Encrypted profile records did not round trip.")
        manager.lock()
        try:
            vault.read("verification/personal")
        except VaultLocked:
            pass
        else:
            raise RuntimeError("Locked encrypted profile allowed a read.")

        # Reconstruct the manager to verify the portable locator and durable data.
        manager = ProfileManager(application)
        manager.unlock(password)
        vault = manager.vault()
        opened.append((vault, vault._keys))
        if (vault.read("verification/personal") != personal
                or vault.read("verification/credential", domain=Domain.CREDENTIAL) != credential):
            raise RuntimeError("Encrypted profile records did not survive reopening.")
    finally:
        try:
            if manager is not None:
                manager.lock()
        finally:
            # Cleanup only the freshly owned direct child of the package state.
            files.ordinary(fixture)
            if fixture.resolve().parent != state:
                raise RuntimeError("Encrypted verification cleanup escaped its fixture directory.")
            shutil.rmtree(fixture)
    if any(vault.state != State.LOCKED or vault._lease is not None
           or vault._keys is not None or any(keys) for vault, keys in opened):
        raise RuntimeError("Encrypted profile verification retained owned resources.")
    return {"crypto_version": nacl.__version__, "vault_round_trip_passed": True,
            "vault_locked_read_denied": True, "vault_owned_resources_released": True,
            "vault_temporary_files_removed": True}


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
    report.update(verify_encrypted_profile(root))
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
