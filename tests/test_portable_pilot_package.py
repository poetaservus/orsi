"""Pilot export must preserve private development data and detect tampering."""
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from tools.assemble_portable_pilot import PUBLIC_FILES, PYTHON_PATHS, assemble, verify_payload


@pytest.fixture
def inputs(tmp_path):
    source, runtime = tmp_path / "source", tmp_path / "fresh-runtime"
    source.mkdir()
    for name in (*PUBLIC_FILES, "app/main.py"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public fixture\n")
    icon = source / "app/ui/assets/orsi.ico"
    icon.parent.mkdir(parents=True)
    icon.write_bytes((Path(__file__).resolve().parents[1] / "app/ui/assets/orsi.ico").read_bytes())
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Package fixture",
        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Public fixture"], check=True)
    python = runtime / "python"
    python.mkdir(parents=True)
    for name in ("python.exe", "pythonw.exe", "python312.dll", "python312.zip"):
        (python / name).write_bytes(b"synthetic runtime")
    (python / "python312._pth").write_text("\n".join(PYTHON_PATHS) + "\n")
    (runtime / "READY.txt").write_text("Inference backend: cloud\n")
    license = python / "Lib/site-packages/demo-1.0.dist-info/licenses/LICENSE"
    license.parent.mkdir(parents=True)
    license.write_text("Public vendor license\n")
    return source, runtime, source / "dist" / "Cloud pilot"


def test_export_uses_committed_public_files_and_never_copies_instance_data(inputs):
    source, runtime, destination = inputs
    private = b"synthetic private development data"
    for name in ("state/selection.json", "profiles/existing/private.bin", ".env", "app/untracked.py"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(private)
    (source / "config/cloud.json").write_bytes(private)
    for name in ("Scripts/pip.exe", "Lib/site-packages/__pycache__/cache.pyc"):
        path = runtime / "python" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(private)

    result = assemble(source, runtime, destination)

    assert result["passed"] and result["fresh_instance_state"]
    assert verify_payload(destination)["passed"]
    assert (destination / "config/cloud.json").read_text() == "public fixture\n"
    assert not list((destination / "state").iterdir()) and not list((destination / "models").iterdir())
    assert not (destination / "profiles").exists()
    assert not (destination / ".git").exists() and not (destination / "tests").exists()
    assert (destination / "runtime/python/Lib/site-packages/demo-1.0.dist-info/licenses/LICENSE").exists()
    assert (destination / "app/ui/assets/orsi.ico").read_bytes() == (source / "app/ui/assets/orsi.ico").read_bytes()
    assert (destination / "Create shortcut.cmd").is_file() and (destination / "tools/create_shortcut.ps1").is_file()
    with zipfile.ZipFile(result["archive"]) as archive:
        assert destination.name + "/state/" in archive.namelist()
        assert destination.name + "/models/" in archive.namelist()
        assert all(private not in archive.read(name) for name in archive.namelist())
        manifest = json.loads(archive.read(destination.name + "/PACKAGE_MANIFEST.json"))
        assert manifest["source_commit"] == result["source_commit"]
    assert (source / "state/selection.json").read_bytes() == private
    assert (source / "profiles/existing/private.bin").read_bytes() == private
    assert (source / "config/cloud.json").read_bytes() == private
    checksum = Path(result["archive"] + ".sha256").read_text()
    assert checksum == result["archive_sha256"] + "  " + Path(result["archive"]).name + "\n"


def test_existing_output_is_preserved(inputs):
    source, runtime, destination = inputs
    destination.mkdir(parents=True)
    (destination / "keep.txt").write_text("Keep existing output")
    with pytest.raises(FileExistsError, match="preserved"):
        assemble(source, runtime, destination)
    assert (destination / "keep.txt").read_text() == "Keep existing output"
    assert not destination.with_suffix(".zip").exists()


@pytest.mark.parametrize("problem", ["import_path", "backend", "missing_python", "extra_state"])
def test_invalid_runtime_fails_before_creating_output(inputs, problem):
    source, runtime, destination = inputs
    if problem == "import_path":
        (runtime / "python/python312._pth").write_text("C:\\synthetic-development-path\nimport site\n")
    elif problem == "backend":
        (runtime / "READY.txt").write_text("Inference backend: cuda\n")
    elif problem == "missing_python":
        (runtime / "python/pythonw.exe").unlink()
    else:
        (runtime / "state").mkdir()
    with pytest.raises(ValueError):
        assemble(source, runtime, destination)
    assert not destination.exists() and not destination.with_suffix(".zip").exists()


@pytest.mark.parametrize("change", ["payload", "state", "profile"])
def test_payload_verification_rejects_tampering_or_personal_data(inputs, change):
    source, runtime, destination = inputs
    assemble(source, runtime, destination)
    if change == "payload":
        (destination / "ORSI.cmd").write_text("changed launcher")
    elif change == "state":
        (destination / "state/selection.json").write_text("unexpected instance state")
    else:
        (destination / "profiles").mkdir()
    with pytest.raises(ValueError):
        verify_payload(destination)
