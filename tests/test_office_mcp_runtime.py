"""Essential pin, relocation, environment and stdio ownership verification."""
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from app.mcp.office_connection import OfficeConnection
from app.mcp.stdio_transport import bridge_environment
from app.portable.deployment import PUBLIC_FILES
from tools.verify_mcp_runtime import verify


ROOT = Path(__file__).resolve().parents[1]


def test_pinned_runtime_verifies_without_office_or_provider_requests():
    report = verify(ROOT)
    assert report["passed"] and report["application_local_modules"]
    assert report["office_processes_started"] == report["provider_requests"] == 0
    assert all(report["licenses_present"].values())
    assert {"requirements-mcp.txt", "config/office_mcp_v1.json", "tools/verify_mcp_runtime.py"} <= set(PUBLIC_FILES)


def test_bridge_environment_does_not_inherit_credentials_or_python_overrides(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "PYTHONPATH", "ORSI_MCP_COMMAND"):
        monkeypatch.setenv(name, "SECRET-ENV-FIXTURE")
    environment = bridge_environment(tmp_path)
    assert "SECRET-ENV-FIXTURE" not in json.dumps(environment)
    assert Path(environment["TEMP"]).is_relative_to(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows portable runtime")
def test_minimal_mcp_runtime_relocates_without_system_python_or_com_installation(tmp_path):
    relocated = tmp_path / "relocated MCP node"
    python_root = relocated / "runtime/python"
    python_root.mkdir(parents=True)
    for source in (ROOT / "runtime/python").iterdir():
        if source.is_file() and source.suffix.lower() in {".exe", ".dll", ".pyd", ".zip", "._pth"}:
            shutil.copy2(source, python_root / source.name)
    requirements = (ROOT / "requirements-mcp.txt").read_text().splitlines()
    packages = {line.split("==")[0] for line in requirements if "==" in line and not line.startswith("#")}
    packages.update(("anyio", "pydantic", "pydantic-core", "typing-extensions", "typing-inspection",
                     "annotated-types", "idna", "h11", "cffi", "pycparser", "openai", "httpx",
                     "httpcore", "sniffio", "certifi", "distro", "jiter", "PyYAML", "langid",
                     "numpy", "pypdf", "defusedxml"))
    for name in packages:
        package = distribution(name)
        for entry in package.files or ():
            if ".." in entry.parts:
                continue  # Executable wrappers in Scripts are deliberately not shipped.
            source = Path(package.locate_file(entry))
            if not source.is_file():
                continue
            destination = python_root / "Lib/site-packages" / entry
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    # ORSI's inference package imports its existing provider modules eagerly.
    # Keep those imports intact; this fixture excludes GUI/GPU/model assets.
    app_files = [source.relative_to(ROOT) for source in (ROOT / "app").rglob("*.py")]
    app_files.extend(Path(name) for name in ("config/office_mcp_v1.json", "config/cloud.json",
                                            "config/model.json", "config/agent.json"))
    for name in app_files:
        destination = relocated / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    probe = """
from pathlib import Path
import sys, mcp, pythoncom, pywintypes, win32api
root = Path(sys.executable).resolve().parent
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in (mcp,pythoncom,pywintypes,win32api))
print('portable MCP and COM imports verified')
"""
    result = subprocess.run([str(python_root / "python.exe"), "-c", probe], cwd=relocated,
        env=bridge_environment(relocated), capture_output=True, text=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    assert "imports verified" in result.stdout
    from app.mcp.office_discovery import OfficeDiscovery
    bridge = OfficeConnection(relocated, backend=lambda: "cloud", discovery=OfficeDiscovery(lambda: ()))
    try:
        assert bridge.connect().ready
        assert not bridge.exposure.eligible  # This fresh-host fixture has no installed Office.
    finally:
        bridge.close()
    assert not bridge.diagnostics["worker_alive"]
