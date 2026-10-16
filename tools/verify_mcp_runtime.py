"""Offline verification of pinned portable MCP modules and application-local DLLs."""
from __future__ import annotations

import argparse
from importlib.metadata import distribution, version
import json
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def verify(root: Path) -> dict:
    root = root.resolve(strict=True)
    runtime = (root / "runtime/python").resolve(strict=True)
    requirements = (root / "requirements-mcp.txt").read_text(encoding="utf-8").splitlines()
    pins = {line.split("==")[0]: line.split("==")[1].split(";")[0].strip()
            for line in requirements if "==" in line and not line.startswith("#")}
    manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if f"mcp=={pins['mcp']}" not in manifest["project"]["dependencies"]:
        raise RuntimeError("The MCP SDK pin differs between runtime manifests.")
    if f"pywin32=={pins['pywin32']}" not in manifest["project"]["optional-dependencies"]["windows"]:
        raise RuntimeError("The Windows automation pin differs between manifests.")
    installed = {name: version(name) for name in pins}
    if installed != pins:
        raise RuntimeError("The portable MCP dependency pins are not installed.")
    import mcp
    import pythoncom
    import pywintypes
    import win32api
    from PIL import Image
    import pypdfium2
    import pypdfium2_raw
    modules = (mcp, pythoncom, pywintypes, win32api, Image, pypdfium2, pypdfium2_raw)
    local = all(Path(module.__file__).resolve().is_relative_to(runtime) for module in modules)
    if not local:
        raise RuntimeError("MCP or Windows automation imports escaped the portable runtime.")
    licenses = {}
    for name in pins:
        package = distribution(name)
        licenses[name] = any(("license" in str(path).lower() or "copying" in str(path).lower())
                             and Path(package.locate_file(path)).is_file() for path in package.files or ())
    if not all(licenses.values()):
        raise RuntimeError("A pinned MCP package is missing bundled license metadata.")
    return {"passed": True, "dependencies": installed, "application_local_modules": local,
            "licenses_present": licenses, "office_processes_started": 0, "provider_requests": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.root)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
