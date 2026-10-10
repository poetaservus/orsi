"""Export a public cloud-only Windows pilot without copying development state."""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import zipfile


PUBLIC_FILES = (
    "ORSI.cmd", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements.txt",
    "config/agent.json", "config/cloud.json", "config/model.json",
    "tools/verify_openai_runtime.py",
)
PYTHON_PATHS = ["python312.zip", ".", "Lib\\site-packages", "..\\..", "import site"]
GUIDE = """O.R.S.I — cloud-only Windows x64 pilot

1. Extract this entire ZIP into a writable folder. Run ORSI.cmd from that folder.
2. Before doing personal work, open Settings > Personal profile > New profile.
   Choose Portable storage, keep its location inside this application folder,
   and enable encryption with your own password. Keep that password safely.
3. In Personal profile > Cloud access, enter your own OpenAI API key.
   Choose whether to enter it each session or explicitly save it encrypted.
   This package contains no credentials and makes no request until you use it.
4. Close O.R.S.I fully before moving or copying the complete application folder.
   Move the profile with it. Keep independent instances in separate folders.
   A profile can be opened by only one instance at a time.

This cloud-only pilot needs internet access and your own API account. It contains
no local model. Physical portable-media and second-PC qualification is pending.
Do not run directly inside the ZIP. PACKAGE_MANIFEST.json inventories the public
payload; the adjacent .zip.sha256 file identifies the original archive.
"""


def ordinary(path: Path) -> None:
    for part in (*reversed(path.absolute().parents), path.absolute()):
        if not part.exists() and not part.is_symlink():
            continue
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Package paths cannot follow filesystem links.")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_file(stream)


def sha256_file(stream) -> str:
    measured = sha256()
    while block := stream.read(1024 * 1024):
        measured.update(block)
    return measured.hexdigest()


def git(source: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(source), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def runtime_files(runtime: Path) -> list[Path]:
    ordinary(runtime)
    if {p.name for p in runtime.iterdir()} != {"python", "READY.txt"}:
        raise ValueError("Use a fresh cloud-only runtime, with no server or download cache.")
    if "Inference backend: cloud" not in (runtime / "READY.txt").read_text(encoding="utf-8-sig"):
        raise ValueError("Runtime is not marked as a verified cloud build.")
    python = runtime / "python"
    for name in ("python.exe", "pythonw.exe", "python312.dll", "python312.zip", "python312._pth"):
        if not (python / name).is_file():
            raise ValueError("Incomplete application-local Python runtime.")
    if (python / "python312._pth").read_text().splitlines() != PYTHON_PATHS:
        raise ValueError("Python import paths must be application-relative.")
    result = []
    for path in sorted(runtime.rglob("*")):
        ordinary(path)
        relative = path.relative_to(runtime)
        if "__pycache__" in relative.parts or relative.parts[:2] == ("python", "Scripts"):
            continue
        if path.is_file() and path.suffix not in {".pyc", ".pyo"}:
            result.append(path)
    return result


def public_export(source: Path, revision: str) -> list[tuple[str, bytes]]:
    archive = git(source, "archive", "--format=tar", revision, "app", *PUBLIC_FILES)
    exported = []
    with tarfile.open(fileobj=BytesIO(archive)) as content:
        for member in content:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name:
                raise ValueError("Invalid public export path.")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Public export contains a link or unsupported entry.")
            if member.name not in PUBLIC_FILES and not (
                    name.parts[0] == "app" and name.suffix in {".py", ".png", ".svg", ".ogg", ".ttf", ".txt"}):
                raise ValueError("Unexpected public application file.")
            exported.append((member.name, content.extractfile(member).read()))
    if not {*PUBLIC_FILES, "app/main.py"} <= {name for name, _ in exported}:
        raise ValueError("Public application export is incomplete.")
    return exported


def verify_payload(root: Path) -> dict:
    """Check a freshly extracted pilot before any application startup writes."""
    ordinary(root)
    manifest = json.loads((root / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in manifest["files"]}
    actual = set()
    for path in root.rglob("*"):
        ordinary(path)
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if name == "PACKAGE_MANIFEST.json":
            continue
        actual.add(name)
        entry = expected.get(name)
        if entry is None or path.stat().st_size != entry["size_bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Pilot payload does not match its inventory.")
    if actual != set(expected) or any((root / "state").iterdir()) or (root / "profiles").exists():
        raise ValueError("Pilot payload is incomplete or contains instance data.")
    return {"passed": True, "files_verified": len(actual), "fresh_instance_state": True}


def assemble(source: Path, runtime: Path, destination: Path) -> dict:
    source, runtime, destination = source.absolute(), runtime.absolute(), destination.absolute()
    ordinary(destination)
    if not destination.resolve().is_relative_to((source / "dist").resolve()):
        raise ValueError("Pilot output must be a new folder under the repository dist directory.")
    archive_path = destination.with_suffix(".zip")
    checksum_path = archive_path.with_suffix(".zip.sha256")
    if any(path.exists() for path in (destination, archive_path, checksum_path)):
        raise FileExistsError("Pilot output already exists; it was preserved.")
    if destination.is_relative_to(runtime) or runtime.is_relative_to(destination):
        raise ValueError("Runtime input and pilot output must be separate.")
    revision = git(source, "rev-parse", "HEAD").decode().strip()
    exported = public_export(source, revision)
    dependencies = runtime_files(runtime)
    destination.mkdir(parents=True)
    for name, data in exported:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for path in dependencies:
        target = destination / "runtime" / path.relative_to(runtime)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (destination / "state").mkdir()
    (destination / "models").mkdir()
    (destination / "START_HERE.txt").write_text(GUIDE, encoding="utf-8")
    inventory = [{"path": path.relative_to(destination).as_posix(),
        "size_bytes": path.stat().st_size, "sha256": digest(path)}
        for path in sorted(destination.rglob("*")) if path.is_file()]
    manifest = {"schema_version": 1, "variant": "cloud-only-windows-x64-pilot",
        "source_commit": revision, "assembler_sha256": digest(Path(__file__)),
        "inventory_excludes": ["PACKAGE_MANIFEST.json"], "files": inventory}
    (destination / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verified = verify_payload(destination)
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for empty in (destination.name + "/state/", destination.name + "/models/"):
            archive.writestr(empty, b"")
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                archive.write(path, destination.name + "/" + path.relative_to(destination).as_posix())
    archive_hash = digest(archive_path)
    checksum_path.write_text(archive_hash + "  " + archive_path.name + "\n", encoding="ascii")
    return {**verified, "source_commit": revision, "archive": str(archive_path),
        "archive_sha256": archive_hash, "archive_bytes": archive_path.stat().st_size,
        "payload_bytes": sum(entry["size_bytes"] for entry in inventory)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(assemble(Path.cwd(), args.runtime, args.destination)))
    except Exception as error:
        print(json.dumps({"passed": False, "error_type": type(error).__name__}))
        raise SystemExit(1)
