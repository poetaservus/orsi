"""Local, bounded installation of SKILL.md only; never execute package code."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import os
from pathlib import Path
import stat
from threading import Lock
from uuid import uuid4

from app.runtime.cancellation import CancellationToken
from app.runtime.skills.contracts import SkillDefinition, SkillLoadError, SkillParseError
from app.runtime.skills.discovery import discover_skills
from app.runtime.skills.loader import _inspect_chain, _read_snapshot, _validate_path
from app.runtime.skills.parser import parse_skill
from app.runtime.skills.registry import SkillRegistry


MAX_INSTALL_SKILLS = 64
MAX_INSTALL_BYTES = 16 * 1024 * 1024
MAX_INSTALL_ENTRIES = 2048
MAX_INSTALL_DEPTH = 8


class SkillInstallErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNSAFE_PATH = "unsafe_path"
    INVALID_PACKAGE = "invalid_package"
    NO_SKILLS = "no_skills"
    DUPLICATE_NAME = "duplicate_name"
    LIMIT_EXCEEDED = "limit_exceeded"
    CONFLICT = "conflict"
    STORAGE_REJECTED = "storage_rejected"
    BUSY = "busy"
    NOT_FOUND = "not_found"
    UNSUPPORTED_RESOURCES = "unsupported_resources"
    IO_ERROR = "io_error"
    REFRESH_FAILED = "refresh_failed"
    ROLLBACK_FAILED = "rollback_failed"
    UNSUPPORTED_PLATFORM = "unsupported_platform"


class SkillInstallError(ValueError):
    def __init__(self, code: SkillInstallErrorCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SkillInstallResult:
    installed: tuple[str, ...] = ()
    already_installed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Package:
    skill: SkillDefinition
    data: bytes


class SkillInstaller:
    """Manage one registry's global storage; project overrides are read-only.

    Complete source validation precedes any storage writes. Existing names are
    accepted only when the stored SKILL.md bytes match exactly (idempotent install).
    Updated content requires explicit removal first; no existing entry is replaced.
    """

    def __init__(self, registry: SkillRegistry | None = None):
        if registry is not None and not isinstance(registry, SkillRegistry):
            raise TypeError("Skill installation requires a SkillRegistry.")
        self.registry = registry if registry is not None else SkillRegistry()
        self._lock = Lock()

    @property
    def storage_root(self) -> Path:
        return self.registry.global_root

    def list(self) -> tuple[SkillDefinition, ...]:
        self._refresh()
        return self.registry.list()

    def info(self, name: str) -> SkillDefinition:
        _validate_name(name)
        self._refresh()
        skill = self.registry.get(name)
        if skill is None:
            raise SkillInstallError(SkillInstallErrorCode.NOT_FOUND, "Skill is not available in the registry.")
        return skill

    def install(self, source: Path, *, on_discovered=None) -> SkillInstallResult:
        if on_discovered is not None and not callable(on_discovered):
            raise TypeError("Installation preview must be callable.")
        packages = _inspect_package(source, self.registry)
        if on_discovered is not None:
            # Detached preview data cannot mutate the validated snapshots.
            from copy import deepcopy
            on_discovered(tuple(deepcopy(p.skill) for p in packages))
        with self._lock:
            created: list[tuple[Path, str]] = []
            installed: list[str] = []
            unchanged: list[str] = []
            try:
                _ensure_directory(self.storage_root)
                with _storage_lock(self.storage_root):
                    try:
                        report = self._global_report()
                        current = {skill.name: skill for skill in report.skills}
                        pending = []
                        for package in packages:
                            existing = current.get(package.skill.name)
                            if existing is not None:
                                if _snapshot(existing.source_path, self.registry.max_bytes) != package.data:
                                    raise SkillInstallError(SkillInstallErrorCode.CONFLICT,
                                                            "An installed name has different content; remove it before reinstalling.")
                                unchanged.append(package.skill.name)
                            else:
                                destination = self.storage_root / _folder_name(package.skill.name)
                                if os.path.lexists(destination):
                                    raise SkillInstallError(SkillInstallErrorCode.CONFLICT,
                                                            "The installation destination already exists.")
                                pending.append((package, destination))
                        # Include files/unknown directories in the discovery capacity.
                        with os.scandir(self.storage_root) as entries:
                            count = sum(1 for _ in entries)
                        if count + len(pending) > self.registry.max_entries:
                            raise SkillInstallError(SkillInstallErrorCode.LIMIT_EXCEEDED,
                                                    "Installation would exceed the registry entry limit.")
                        for package, destination in pending:
                            stage = self.storage_root.parent / (".orsi-skill-stage-" + uuid4().hex)
                            identity = _create_directory(stage)
                            created.append((stage, identity))
                            _write_package(stage, identity, package.data)
                        # Staging is outside discovery storage. Publish without replacement.
                        for index, (package, destination) in enumerate(pending):
                            stage, identity = created[index]
                            _publish(stage, destination, identity)
                            created[index] = (destination, identity)
                            _verify_package(destination, identity, package.data)
                            installed.append(package.skill.name)
                        self._refresh()
                        refreshed = self._global_report()
                        names = {skill.name for skill in refreshed.skills}
                        if any(p.skill.name not in names for p in packages):
                            raise SkillInstallError(SkillInstallErrorCode.REFRESH_FAILED,
                                                    "Installed skills were rejected during registry refresh.")
                    except BaseException:
                        self._rollback(created)
                        raise
            except SkillInstallError:
                raise
            except (SkillLoadError, SkillParseError):
                raise SkillInstallError(SkillInstallErrorCode.STORAGE_REJECTED,
                                        "Skill storage is unsafe or contains rejected content.") from None
            except OSError:
                raise SkillInstallError(SkillInstallErrorCode.IO_ERROR,
                                        "Skill installation could not complete safely.") from None
            return SkillInstallResult(tuple(installed), tuple(unchanged))

    def remove(self, name: str) -> None:
        _validate_name(name)
        _check_platform()
        with self._lock:
            try:
                _inspect_chain(self.storage_root, self.storage_root)
                with _storage_lock(self.storage_root):
                    skill = next((s for s in self._global_report().skills if s.name == name), None)
                    if skill is None:
                        raise SkillInstallError(SkillInstallErrorCode.NOT_FOUND,
                                                "Skill is not installed in global storage.")
                    from app.execution.windows_filesystem import directory_identity_for_path
                    identity = directory_identity_for_path(skill.root_path)
                    _check_leaf(skill.root_path, identity)
                    quarantine = self.storage_root.parent / (".orsi-skill-remove-" + uuid4().hex)
                    _publish(skill.root_path, quarantine, identity)
                    try:
                        self._refresh()
                    except BaseException:
                        try:
                            _publish(quarantine, skill.root_path, identity)
                            self._refresh()
                        except Exception:
                            raise SkillInstallError(SkillInstallErrorCode.ROLLBACK_FAILED,
                                                    "Removal could not restore storage and refresh the registry.") from None
                        raise
                    try:
                        _discard(quarantine, identity)
                    except OSError:
                        raise SkillInstallError(SkillInstallErrorCode.IO_ERROR,
                                                "Skill was removed from discovery; quarantined content could not be cleaned up.") from None
            except FileNotFoundError:
                raise SkillInstallError(SkillInstallErrorCode.NOT_FOUND, "Skill is not installed in global storage.") from None
            except SkillLoadError:
                raise SkillInstallError(SkillInstallErrorCode.UNSAFE_PATH, "Skill storage is unsafe.") from None
            except OSError:
                raise SkillInstallError(SkillInstallErrorCode.IO_ERROR, "Skill removal could not complete safely.") from None

    def _global_report(self):
        report = discover_skills(global_root=self.storage_root, max_bytes=self.registry.max_bytes,
                                 max_entries=self.registry.max_entries)
        if report.issues:
            raise SkillInstallError(SkillInstallErrorCode.STORAGE_REJECTED,
                                    "Global storage contains rejected entries; resolve them before changing skills.")
        return report

    def _refresh(self):
        try:
            return self.registry.reload()
        except Exception:
            raise SkillInstallError(SkillInstallErrorCode.REFRESH_FAILED, "Skill registry refresh failed.") from None

    def _rollback(self, created):
        failed = False
        for folder, identity in reversed(created):
            try:
                _discard(folder, identity)
            except Exception:
                failed = True
        try:
            self._refresh()
        except Exception:
            failed = True
        if failed:
            raise SkillInstallError(SkillInstallErrorCode.ROLLBACK_FAILED,
                                    "Installation rollback or registry refresh could not be completed safely.") from None


def _check_platform():
    if os.name != "nt":
        raise SkillInstallError(SkillInstallErrorCode.UNSUPPORTED_PLATFORM,
                                "Safe local skill installation is supported on Windows only.")


def _validate_name(name):
    if not isinstance(name, str) or not name.strip():
        raise SkillInstallError(SkillInstallErrorCode.INVALID_INPUT, "Skill names must be nonempty strings.")


def _inspect_package(source, registry) -> tuple[_Package, ...]:
    if not isinstance(source, Path):
        raise SkillInstallError(SkillInstallErrorCode.INVALID_INPUT, "Installation requires a local directory path.")
    _check_platform()
    packages, seen = [], set()
    entries, total = 0, 0
    try:
        _validate_path(source, source)
        root = Path(os.path.abspath(source))
        from app.execution.windows_filesystem import pinned_parent
        def visit(folder, depth):
            nonlocal entries, total
            info = _inspect_chain(folder, folder)
            if not stat.S_ISDIR(info.st_mode):
                raise SkillInstallError(SkillInstallErrorCode.INVALID_INPUT, "Installation source must be a directory.")
            with pinned_parent(folder / "SKILL.md", CancellationToken()):
                skill_path = folder / "SKILL.md"
                if os.path.lexists(skill_path):
                    data = _snapshot(skill_path, registry.max_bytes)
                    skill = parse_skill(data.decode("utf-8", errors="strict"), root_path=folder, source_path=skill_path)
                    if skill.name in seen:
                        raise SkillInstallError(SkillInstallErrorCode.DUPLICATE_NAME,
                                                "Source contains duplicate skill names; nothing was installed.")
                    seen.add(skill.name)
                    total += len(data)
                    if len(packages) >= MAX_INSTALL_SKILLS or total > MAX_INSTALL_BYTES:
                        raise SkillInstallError(SkillInstallErrorCode.LIMIT_EXCEEDED, "Source exceeds installation size limits.")
                    packages.append(_Package(skill, data))
                    return  # Other content inside a skill is unsupported and never traversed.
                children = []
                with os.scandir(folder) as scan:
                    for child in scan:
                        entries += 1
                        if entries > MAX_INSTALL_ENTRIES:
                            raise SkillInstallError(SkillInstallErrorCode.LIMIT_EXCEEDED, "Source exceeds the inspection entry limit.")
                        children.append(Path(child.path))
                for child in sorted(children, key=lambda p: (p.name.casefold(), p.name)):
                    child_info = child.lstat()
                    if stat.S_ISLNK(child_info.st_mode) or getattr(child_info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        raise SkillInstallError(SkillInstallErrorCode.UNSAFE_PATH, "Source inspection rejects symlinks and reparse points.")
                    if stat.S_ISDIR(child_info.st_mode):
                        if depth >= MAX_INSTALL_DEPTH:
                            raise SkillInstallError(SkillInstallErrorCode.LIMIT_EXCEEDED, "Source exceeds the inspection depth limit.")
                        visit(child, depth + 1)
        visit(root, 0)
    except SkillInstallError:
        raise
    except SkillLoadError as error:
        code = SkillInstallErrorCode.UNSAFE_PATH if error.code.value == "unsafe_path" else SkillInstallErrorCode.INVALID_PACKAGE
        raise SkillInstallError(code, "Source skill could not be loaded safely; nothing was installed.") from None
    except (SkillParseError, UnicodeError, ValueError):
        raise SkillInstallError(SkillInstallErrorCode.INVALID_PACKAGE, "Source contains a malformed skill; nothing was installed.") from None
    except OSError:
        raise SkillInstallError(SkillInstallErrorCode.IO_ERROR, "Source directory could not be inspected safely.") from None
    if not packages:
        raise SkillInstallError(SkillInstallErrorCode.NO_SKILLS, "Source contains no supported SKILL.md files.")
    return tuple(sorted(packages, key=lambda p: p.skill.name))


def _snapshot(path, max_bytes):
    _validate_path(path, path)
    info = _inspect_chain(path, path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise SkillInstallError(SkillInstallErrorCode.INVALID_PACKAGE, "SKILL.md must be a bounded regular file.")
    return _read_snapshot(path, max_bytes)


def _folder_name(name):
    # Untrusted metadata is never used as a filesystem component.
    return "skill-" + sha256(name.encode("utf-8", errors="surrogatepass")).hexdigest()


def _ensure_directory(folder):
    _validate_path(folder, folder)
    missing, current = [], folder
    while not os.path.lexists(current):
        missing.append(current)
        current = current.parent
    info = _inspect_chain(current, folder)
    if not stat.S_ISDIR(info.st_mode):
        raise SkillInstallError(SkillInstallErrorCode.STORAGE_REJECTED, "Storage ancestor must be a directory.")
    for child in reversed(missing):
        _create_directory(child)
    _inspect_chain(folder, folder)


def _create_directory(folder):
    from app.execution.windows_filesystem import create_child_directory, pinned_parent
    with pinned_parent(folder, CancellationToken()) as (parent, _identity):
        return create_child_directory(parent, folder.name)


@contextmanager
def _storage_lock(root):
    from app.execution.windows_filesystem import pinned_parent
    with pinned_parent(root / ".orsi-install.lock", CancellationToken()):
        # Keep the lock outside discovery so a full catalog can still be removed.
        lock_path = _lock_path(root)
        try:
            stream = lock_path.open("xb")
        except FileExistsError:
            raise SkillInstallError(SkillInstallErrorCode.BUSY, "Skill storage is locked by another operation.") from None
        try:
            yield
        finally:
            stream.close()
            lock_path.unlink()


def _lock_path(root):
    identity = sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
    return root.parent / (".orsi-skill-lock-" + identity + ".lock")


def _write_package(folder, identity, data):
    from app.execution.windows_filesystem import pinned_parent
    with pinned_parent(folder / "SKILL.md", CancellationToken()) as (_, actual):
        if actual != identity:
            raise SkillInstallError(SkillInstallErrorCode.UNSAFE_PATH, "Staging directory changed unexpectedly.")
        with (folder / "SKILL.md").open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if _snapshot(folder / "SKILL.md", len(data)) != data:
            raise SkillInstallError(SkillInstallErrorCode.IO_ERROR, "Copied skill did not match the validated snapshot.")


def _publish(source, destination, identity):
    from app.execution.windows_filesystem import directory_identity_for_path, pinned_parent
    with pinned_parent(source, CancellationToken()), pinned_parent(destination, CancellationToken()):
        if directory_identity_for_path(source) != identity:
            raise SkillInstallError(SkillInstallErrorCode.UNSAFE_PATH, "Package directory changed before placement.")
        os.rename(source, destination)  # Windows fails on any existing destination.


def _verify_package(folder, identity, data):
    from app.execution.windows_filesystem import pinned_parent
    with pinned_parent(folder / "SKILL.md", CancellationToken()):
        _check_leaf(folder, identity)
        if _snapshot(folder / "SKILL.md", len(data)) != data:
            raise SkillInstallError(SkillInstallErrorCode.IO_ERROR,
                                    "Placed skill did not match the validated snapshot.")


def _check_leaf(folder, identity):
    from app.execution.windows_filesystem import pinned_parent
    with pinned_parent(folder / "SKILL.md", CancellationToken()) as (_, actual):
        if actual != identity:
            raise SkillInstallError(SkillInstallErrorCode.UNSAFE_PATH, "Package directory changed before cleanup.")
        with os.scandir(folder) as scan:
            if any(entry.name != "SKILL.md" for entry in scan):
                raise SkillInstallError(SkillInstallErrorCode.UNSUPPORTED_RESOURCES,
                                        "Removal only supports directories containing SKILL.md alone.")
        if os.path.lexists(folder / "SKILL.md"):
            _inspect_chain(folder / "SKILL.md", folder)


def _discard(folder, identity):
    from app.execution.windows_filesystem import pinned_parent
    with pinned_parent(folder / "SKILL.md", CancellationToken()):
        _check_leaf(folder, identity)
        (folder / "SKILL.md").unlink(missing_ok=True)
    folder.rmdir()  # Empty directory only. Never perform recursive deletion.
