"""Build relocatable Windows nodes without Git, downloads or plaintext exports."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from threading import Lock
from uuid import uuid4

from app.portable.identity import DEPLOYMENT_DISABLED, NODE_MANIFEST, is_deployed_node, node_name
from app.portable.volumes import finish_drive_label, prepare_drive_label
from app.runtime.cancellation import CancellationToken
from app.state.storage import JsonStore
from app.vault import files
from app.vault.types import VaultError


PUBLIC_FILES = ("ORSI.cmd", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements.txt",
                "requirements-mcp.txt", "config/office_mcp_v1.json",
                "config/agent.json", "config/cloud.json", "config/model.json",
                "tools/verify_openai_runtime.py", "tools/verify_mcp_runtime.py",
                "Create shortcut.cmd", "tools/create_shortcut.ps1")
APP_SUFFIXES = {".py", ".png", ".ico", ".svg", ".ogg", ".ttf", ".txt", ".md"}
PYTHON_PATHS = ["python312.zip", ".", "Lib\\site-packages", "..\\..", "import site"]
PROFILE_FOLDER = "profiles/current"
MANIFEST = NODE_MANIFEST
_NUMBER_LOCK = Lock()


class DeploymentError(VaultError):
    """Fixed user-facing deployment errors, without exception contents."""


@dataclass(frozen=True)
class DeploymentResult:
    destination: Path
    includes_profile: bool
    includes_models: bool
    files_verified: int
    bytes_copied: int
    copy_registered: bool = True
    node_number: int = 1
    drive_label: str | None = None
    drive_message: str = ""


def _reserve_number(root):
    # Reservations may leave gaps on cancellation, but never reuse a node name.
    with _NUMBER_LOCK:
        store = JsonStore(root / "state/portable_deployment_v1.json")
        try:
            files.ordinary(store.path)
            data = store.load({"version": 1, "next_number": 1})
            if (not isinstance(data, dict) or set(data) != {"version", "next_number"}
                    or data["version"] != 1 or type(data["next_number"]) is not int
                    or not 1 <= data["next_number"] <= 999999):
                raise ValueError()
            number = data["next_number"]
            store.save({"version": 1, "next_number": number + 1})
            return number
        except (OSError, ValueError, TypeError):
            raise DeploymentError("The next portable node number could not be saved. Check this installation's state folder.") from None


def _digest(path, token):
    measured = sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            token.raise_if_cancelled()
            measured.update(block)
    return measured.hexdigest()


def _tree(root, *, keep=lambda path: True):
    for path, size in files.iter_files(root):
        if keep(path.relative_to(root)):
            yield path, size


def _runtime_keep(path, include_models):
    if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"} or path.parts[0] == "Scripts":
        return False
    if not include_models and path.parts[:2] == ("Lib", "site-packages") and len(path.parts) > 2:
        package = path.parts[2].lower()
        if package in {"nvidia", "llama_cpp"} or package.startswith(("nvidia_", "llama_cpp_python-")):
            return False
    return True


def _payload(root, include_models):
    paths = []
    for name in ("app/main.py", "app/__init__.py"):
        files.ordinary(root / name)
        if not (root / name).is_file():
            raise DeploymentError("Application files are missing. Repair this installation before deploying a node.")
    for name in PUBLIC_FILES:
        path = root / name
        files.ordinary(path)
        if not path.is_file():
            raise DeploymentError("Application files are missing. Repair this installation before deploying a node.")
        paths.append((path, name, path.stat().st_size))
    paths.extend((path, "app/" + path.relative_to(root / "app").as_posix(), size)
                 for path, size in _tree(root / "app", keep=lambda p: "__pycache__" not in p.parts and p.suffix in APP_SUFFIXES))
    python = root / "runtime/python"
    for name in ("python.exe", "pythonw.exe", "python312.dll", "python312.zip", "python312._pth"):
        files.ordinary(python / name)
        if not (python / name).is_file():
            raise DeploymentError("The portable Python runtime is incomplete. Repair this installation before deploying.")
    if (python / "python312._pth").read_text().splitlines() != PYTHON_PATHS:
        raise DeploymentError("This Python runtime does not use portable paths. Repair it before deploying a node.")
    paths.extend((path, "runtime/python/" + path.relative_to(python).as_posix(), size)
                 for path, size in _tree(python, keep=lambda p: _runtime_keep(p, include_models)))
    if include_models:
        server = root / "runtime/llama-server"
        if not (server / "llama-server.exe").is_file():
            raise DeploymentError("Local model support is not installed. Choose cloud-only or install local support first.")
        models = list(_tree(root / "models", keep=lambda p: p.suffix.lower() == ".gguf" or
                            p.name.upper().startswith(("LICENSE", "COPYING"))))
        if not any(path.suffix.lower() == ".gguf" and not path.name.startswith("mmproj-") for path, _ in models):
            raise DeploymentError("No local models are installed. Choose cloud-only or install a model first.")
        paths.extend((path, "runtime/llama-server/" + path.relative_to(server).as_posix(), size)
                     for path, size in _tree(server, keep=lambda p: p.suffix.lower() in {".dll", ".exe", ".txt", ".md"}
                                             or p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))))
        paths.extend((path, "models/" + path.relative_to(root / "models").as_posix(), size) for path, size in models)
    return paths


def _destination(manager, destination):
    destination = Path(destination).absolute()
    files.ordinary(destination)
    destination = Path(os.path.abspath(destination))
    if destination.exists():
        raise DeploymentError("This destination already exists. Choose a new node folder; existing files were preserved.")
    protected = {manager.application_root / name for name in ("app", "config", "runtime", "models", "tools", "state", "profiles")}
    protected.update(manager.known_roots)
    protected.add(manager.application_root)
    if any(destination.is_relative_to(root) or root.is_relative_to(destination)
           for root in (Path(os.path.abspath(path)) for path in protected)):
        raise DeploymentError("Choose a new folder outside this installation and its profiles.")
    if not destination.parent.is_dir():
        raise DeploymentError("Choose an existing destination folder or reconnect its drive.")
    return destination


def _remove_staging(staging, parent):
    # Delete only the unique direct child created by this deployment.
    if staging.parent != parent or staging.resolve().parent != parent.resolve() or not staging.name.startswith(".orsi-node-"):
        raise DeploymentError("The unfinished node could not be cleaned up safely.")
    files.ordinary(staging)
    if staging.exists():
        shutil.rmtree(staging)


def verify_node(root, *, token=None, progress=lambda value, label: None):
    """Verify a new node before first launch changes its private state."""
    root, token = Path(root), token or CancellationToken()
    files.ordinary(root)
    value = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in value["files"]}
    actual = list(_tree(root))
    seen = set()
    for index, (path, size) in enumerate(actual):
        token.raise_if_cancelled()
        name = path.relative_to(root).as_posix()
        if name == MANIFEST:
            continue
        seen.add(name)
        entry = expected.get(name)
        if entry is None or size != entry["size_bytes"] or _digest(path, token) != entry["sha256"]:
            raise DeploymentError("Node verification failed. The destination may have changed or its drive may be unreliable.")
        progress(85 + int(14 * (index + 1) / max(1, len(actual))), "Verifying node…")
    if seen != set(expected):
        raise DeploymentError("Node verification failed because files are missing.")
    return len(seen)


def deploy_node(manager, destination, *, include_profile=True, include_models=False,
                token=None, progress=lambda value, label: None):
    """Publish a complete new folder, preserving source selection and contents."""
    if is_deployed_node(manager.application_root):
        raise DeploymentError(DEPLOYMENT_DISABLED)
    token = token or CancellationToken()
    token.raise_if_cancelled()
    manager._check_deletion()
    destination = _destination(manager, destination)
    session = manager.session if include_profile else None
    if include_profile:
        if session is None or manager.locator is None:
            raise DeploymentError("Unlock or open your profile before including it in a node.")
        session.require_active()
    progress(0, "Preparing node…")
    payload = _payload(manager.application_root, include_models)
    profile_size = sum(size for _, size in _tree(manager.locator.root)) if include_profile else 0
    total = sum(size for _, _, size in payload) + profile_size
    if shutil.disk_usage(destination.parent).free < total + max(64 * 1024**2, total // 20):
        raise DeploymentError("There is not enough free space on the destination drive for this node.")
    token.raise_if_cancelled()
    number = _reserve_number(manager.application_root)
    drive_plan = prepare_drive_label(destination.parent, manager.application_root, number)
    staging = destination.parent / (".orsi-node-" + uuid4().hex + ".partial")
    staging.mkdir()
    copied, inventory = 0, []
    phase = "Copying node…"

    def copy_file(source, target):
        nonlocal copied
        token.raise_if_cancelled()
        files.ordinary(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        measured = sha256()
        size = source.stat().st_size
        with files.snapshot(source, size) as input_file, target.open("xb") as output:
            while block := input_file.read(1024 * 1024):
                token.raise_if_cancelled()
                output.write(block)
                measured.update(block)
                copied += len(block)
                progress(min(84, int(84 * copied / max(1, total))), phase)
        inventory.append({"path": target.relative_to(staging).as_posix(),
                          "size_bytes": target.stat().st_size, "sha256": measured.hexdigest()})

    def write_json(name, value):
        path = staging / name
        JsonStore(path).save(value)
        inventory.append({"path": name, "size_bytes": path.stat().st_size, "sha256": _digest(path, token)})

    try:
        (staging / "state").mkdir()
        (staging / "models").mkdir()
        for source, name, _ in payload:
            copy_file(source, staging / name)
        if include_profile:
            session.require_active()
            profile = staging / PROFILE_FOLDER
            profile.parent.mkdir()
            phase = "Copying your profile…"
            progress(min(84, int(84 * copied / max(1, total))), "Copying your profile…")
            if session.encrypted:
                session._vault.export_copy(profile, copy_file=copy_file, check_cancelled=token.raise_if_cancelled)
            else:
                profile.mkdir()
                for source, _ in _tree(session._vault.root, keep=lambda p: p.as_posix() != ".lease"):
                    copy_file(source, profile / source.relative_to(session._vault.root))
                for entry in inventory:
                    if entry["path"].startswith(PROFILE_FOLDER + "/"):
                        source = session._vault.root / entry["path"].removeprefix(PROFILE_FOLDER + "/")
                        if _digest(source, token) != entry["sha256"]:
                            raise DeploymentError("The profile changed during deployment. Wait for other work to finish, then retry.")
            session.require_active()
            locator = manager.locator
            write_json("state/profile_locator_v1.json", {"version": 1, "location": PROFILE_FOLDER,
                "relative": True, "mode": "portable", "encrypted": session.encrypted, "profile_id": locator.profile_id})
            write_json("state/profile_registry_v1.json", {"version": 1, "copies": [{"location": PROFILE_FOLDER,
                "relative": True, "encrypted": session.encrypted, "profile_id": locator.profile_id}]})
        guide = (node_name(number) + "\n\nRun ORSI.cmd from this folder.\n" +
                 ("Unlock the included profile with its existing password or recovery key.\n" if include_profile and session.encrypted else
                  "This node includes your current unencrypted profile.\n" if include_profile else "Create your own profile when O.R.S.I opens.\n") +
                 ("Installed local models are included.\n" if include_models else "This cloud-only node needs internet access and a cloud connection.\n") +
                 "Close O.R.S.I before moving the complete folder, including profiles.\n"
                 "Deploy new nodes from the local O.R.S.I app; this portable node cannot deploy others.\n")
        for name, text in (("START_HERE.txt", guide), ("runtime/READY.txt", "Inference backend: " + ("local + cloud" if include_models else "cloud") + "\n")):
            path = staging / name
            path.write_text(text, encoding="utf-8")
            inventory.append({"path": name, "size_bytes": path.stat().st_size, "sha256": _digest(path, token)})
        JsonStore(staging / MANIFEST).save({"schema_version": 1, "variant": "portable-windows-x64-node",
            "includes_profile": include_profile, "includes_local_models": include_models,
            "node_number": number, "node_name": node_name(number), "can_deploy_nodes": False,
            "files": sorted(inventory, key=lambda entry: entry["path"])})
        count = verify_node(staging, token=token, progress=progress)
        token.raise_if_cancelled()
        if include_profile:
            session.require_active()
        if destination.exists():
            raise DeploymentError("The destination was created during deployment. Its existing files were preserved.")
        staging.rename(destination)
    except BaseException:
        _remove_staging(staging, destination.parent)
        raise
    registered = True
    if include_profile:
        try:
            manager.copies.remember(destination / PROFILE_FOLDER, locator.profile_id, session.encrypted, portable=True)
            manager.known_roots.add(destination / PROFILE_FOLDER)
        except Exception:
            registered = False
    drive = finish_drive_label(drive_plan, destination)
    progress(100, "Node ready")
    return DeploymentResult(destination, include_profile, include_models, count, copied, registered,
                            number, drive.label, drive.message)
