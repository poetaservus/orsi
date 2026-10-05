"""Inspect public HTTPS Git repositories as data; never check out or run them."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import uuid4

from app.runtime.cancellation import CancellationToken
from app.runtime.skills.installer import (
    MAX_INSTALL_BYTES, MAX_INSTALL_SKILLS, SkillInstaller, SkillInstallError,
    SkillInstallErrorCode as Code, _check_platform, _create_directory, _inspect_package,
)
from app.runtime.skills.package_format import (
    ReferenceFile, MAX_REFERENCE_BYTES, MAX_REFERENCE_FILES, MAX_TOTAL_REFERENCE_BYTES,
    validate_reference_path, validate_references,
)


MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_REPOSITORY_BLOB_BYTES = 32 * 1024 * 1024
MAX_TREE_BYTES = 8 * 1024 * 1024
MAX_TREE_ENTRIES = 4096
DOWNLOAD_TIMEOUT = 120.0
_OID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


@dataclass(frozen=True, slots=True)
class GitSkillInstallResult:
    installed: tuple[str, ...]
    already_installed: tuple[str, ...]
    revision: str


@dataclass(frozen=True, slots=True)
class GitSkillSnapshot:
    packages: tuple
    revision: str


class GitSkillInstaller:
    """Reuse the local install transaction after all download resources are released.

    Only the remote's default branch tip is inspected. No credentials, URL refs,
    submodules, symlinks, checkout filters, hooks or dependency installers are used.
    """

    def __init__(self, installer: SkillInstaller | None = None):
        if installer is not None and not isinstance(installer, SkillInstaller):
            raise TypeError("Git skill installation requires a SkillInstaller.")
        self.installer = installer if installer is not None else SkillInstaller()

    def install(self, url: str, *, on_discovered=None,
                cancellation: CancellationToken | None = None) -> GitSkillInstallResult:
        _validate_url(url)
        _check_platform()
        if on_discovered is not None and not callable(on_discovered):
            raise TypeError("Installation preview must be callable.")
        if cancellation is not None and not isinstance(cancellation, CancellationToken):
            raise TypeError("Git installation requires a CancellationToken.")
        token = cancellation if cancellation is not None else CancellationToken()
        deadline = monotonic() + DOWNLOAD_TIMEOUT
        _boundary(token, deadline)
        snapshot = self._prepare(url, token, deadline)
        _boundary(token, deadline)
        def preview(skills):
            _boundary(token, deadline)
            if on_discovered is not None:
                on_discovered(skills)
            _boundary(token, deadline)
        result = self.installer._install_packages(snapshot.packages, on_discovered=preview)
        return GitSkillInstallResult(result.installed, result.already_installed, snapshot.revision)

    def prepare(self, url: str, *, cancellation: CancellationToken | None = None) -> GitSkillSnapshot:
        """Inspect immutable package bytes and release the clone without publication."""
        _validate_url(url)
        _check_platform()
        if cancellation is not None and not isinstance(cancellation, CancellationToken):
            raise TypeError("Git inspection requires a CancellationToken.")
        token = cancellation if cancellation is not None else CancellationToken()
        return self._prepare(url, token, monotonic() + DOWNLOAD_TIMEOUT)

    def _prepare(self, url, token, deadline):
        _boundary(token, deadline)
        executable = shutil.which("git")
        if executable is None:
            raise SkillInstallError(Code.GIT_UNAVAILABLE, "Git is required for HTTPS skill installation.")
        try:
            with _workspace() as root:
                empty = root / "empty-template"
                empty.mkdir()
                command = _Git(executable, root, empty, token, deadline)
                repository = root / "repository.git"
                command.clone(url, repository)
                revision = command.read(repository, ["rev-parse", "--verify", "HEAD^{commit}"], 66).strip()
                if not _OID.fullmatch(revision):
                    raise SkillInstallError(Code.UNSAFE_REPOSITORY, "Repository has no valid default-branch revision.")
                tree = command.read(repository, ["ls-tree", "--full-tree", "-l", "-r", "-z",
                                                 revision.decode("ascii")], MAX_TREE_BYTES)
                blobs = _package_blobs(tree, self.installer.registry.max_bytes)
                materialized = root / "skills"
                materialized.mkdir()
                for index, documents in enumerate(blobs):
                    # Original repository roots remain opaque. Only validated
                    # package-relative reference identifiers become child paths.
                    folder = materialized / f"package-{index:04d}"
                    folder.mkdir()
                    for relative, oid, size in documents:
                        data = command.read(repository, ["cat-file", "blob", oid], size)
                        if len(data) != size:
                            raise SkillInstallError(Code.UNSAFE_REPOSITORY, "Repository object size changed during inspection.")
                        target = folder / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with target.open("xb") as stream:
                            stream.write(data)
                packages = _inspect_package(materialized, self.installer.registry)
                _boundary(token, deadline)
            # Cleanup failure prevents publication. Snapshots have no dependency on
            # the now-deleted clone or synthetic paths retained for preview metadata.
            _boundary(token, deadline)
            return GitSkillSnapshot(packages, revision.decode("ascii"))
        except SkillInstallError:
            raise
        except (OSError, ValueError):
            raise SkillInstallError(Code.DOWNLOAD_FAILED, "Git repository could not be inspected safely.") from None


def _validate_url(url):
    try:
        if (not isinstance(url, str) or not 1 <= len(url) <= 2048
                or any(ord(c) < 33 or ord(c) > 126 for c in url) or "\\" in url):
            raise ValueError
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment
                or "?" in url or "#" in url or not parts.path.strip("/")
                or parts.port is not None and not 1 <= parts.port <= 65535):
            raise ValueError
        host = parts.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                       for label in host.split(".")):
                raise ValueError
        # Percent-encoded delimiters/credentials/control bytes are unnecessary for
        # this deliberately narrow public repository URL interface.
        if "%" in parts.netloc or re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f|2f|5c)", parts.path, re.I):
            raise ValueError
    except (ValueError, TypeError):
        raise SkillInstallError(Code.INVALID_REMOTE, "Use a public HTTPS repository URL without credentials, queries or fragments.") from None


def _environment():
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("GIT_", "GCM_"))
           and key.upper() not in {"SSH_ASKPASS", "SSH_ASKPASS_REQUIRE"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               GCM_INTERACTIVE="never", GIT_LFS_SKIP_SMUDGE="1")
    return env


class _Git:
    def __init__(self, executable, root, empty, token, deadline):
        self.root, self.token, self.deadline = root, token, deadline
        self.env = _environment()
        self.prefix = [executable, "-c", f"core.hooksPath={empty}", "-c", "core.fsmonitor=false",
                       "-c", "credential.helper=", "-c", "core.askPass=", "-c", "protocol.allow=never",
                       "-c", "protocol.https.allow=always", "-c", "http.followRedirects=false",
                       "-c", "maintenance.auto=false", "-c", "gc.auto=0",
                       "-c", "fetch.unpackLimit=1", "-c", "fetch.fsckObjects=true",
                       "-c", "transfer.fsckObjects=true"]
        self.empty = empty

    def clone(self, url, repository):
        self.run(["clone", "--bare", "--depth=1", "--single-branch", "--no-tags", "--no-local",
                  f"--template={self.empty}", "--", url, str(repository)], 0)

    def read(self, repository, arguments, limit):
        return self.run(["--git-dir=" + str(repository), *arguments], limit)

    def run(self, arguments, limit):
        from app.runtime.skills._git_process import start_owned_process
        _boundary(self.token, self.deadline)
        output = self.root / ("output-" + uuid4().hex)
        process = None
        try:
            with output.open("xb") as stream:
                process = start_owned_process(self.prefix + arguments, cwd=self.root,
                                              env=self.env, stdout=stream.fileno())
                while True:
                    _boundary(self.token, self.deadline)
                    _check_download(self.root)
                    if output.stat().st_size > limit:
                        raise SkillInstallError(Code.DOWNLOAD_LIMIT, "Git output exceeds its inspection limit.")
                    status = process.poll()
                    if status is not None:
                        break
                    sleep(0.05)
                if status != 0:
                    raise SkillInstallError(Code.DOWNLOAD_FAILED, "Git download or object inspection failed.")
            # Closing the job also stops descendants which outlive the Git parent.
            process.close()
            _boundary(self.token, self.deadline)
            _check_download(self.root)
            with output.open("rb") as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise SkillInstallError(Code.DOWNLOAD_LIMIT, "Git output exceeds its inspection limit.")
            return data
        finally:
            if process is not None:
                process.close()
            if output.exists():
                _delete_file(output)


def _boundary(token, deadline):
    if token.is_cancelled:
        raise SkillInstallError(Code.CANCELLED, "Git skill installation was cancelled before publication.")
    if monotonic() >= deadline:
        raise SkillInstallError(Code.TIMED_OUT, "Git skill inspection exceeded its deadline.")


def _package_blobs(tree, max_skill_bytes):
    if not tree or not tree.endswith(b"\0"):
        raise SkillInstallError(Code.NO_SKILLS if not tree else Code.UNSAFE_REPOSITORY,
                                "Repository contains no supported skills or has an invalid tree.")
    records = tree[:-1].split(b"\0")
    if len(records) > MAX_TREE_ENTRIES:
        raise SkillInstallError(Code.DOWNLOAD_LIMIT, "Repository exceeds the tree entry limit.")
    objects, paths = {}, set()
    for record in records:
        try:
            header, path = record.split(b"\t", 1)
            mode, kind, oid, size = header.split()
            if (not path or path in paths or not _OID.fullmatch(oid)
                    or mode not in (b"100644", b"100755") or kind != b"blob"
                    or not size.isdigit()):
                raise ValueError
            paths.add(path)
            length = int(size)
        except ValueError:
            raise SkillInstallError(Code.UNSAFE_REPOSITORY,
                                    "Repository rejects symlinks, submodules and unsupported tree entries.") from None
        if length > MAX_REPOSITORY_BLOB_BYTES:
            raise SkillInstallError(Code.DOWNLOAD_LIMIT, "Repository contains an oversized file.")
        objects[path] = (oid.decode("ascii"), length)
    roots = []
    for path in sorted(objects, key=lambda item: (len(item), item)):
        if path.rsplit(b"/", 1)[-1] == b"SKILL.md":
            # Match local discovery: an entry point defines the whole package;
            # nested entry points do not silently install additional skills.
            if not any(path.startswith(root) for root in roots):
                roots.append(path[:-len(b"SKILL.md")])
    blobs, total = [], 0
    for root in roots:
        oid, length = objects[root + b"SKILL.md"]
        if length > max_skill_bytes or len(blobs) >= MAX_INSTALL_SKILLS:
            raise SkillInstallError(Code.LIMIT_EXCEEDED, "Repository skills exceed installation size limits.")
        documents, reference_bytes = [("SKILL.md", oid, length)], 0
        for path in sorted(objects):
            if not path.startswith(root + b"references/") or not path.endswith(b".md"):
                continue
            try:
                relative = path[len(root):].decode("ascii")
                validate_reference_path(relative)
            except ValueError:
                raise SkillInstallError(Code.UNSAFE_REPOSITORY, "Repository references contain unsupported paths.") from None
            reference_oid, reference_size = objects[path]
            reference_bytes += reference_size
            if (reference_size > MAX_REFERENCE_BYTES or reference_bytes > MAX_TOTAL_REFERENCE_BYTES
                    or len(documents) > MAX_REFERENCE_FILES):
                raise SkillInstallError(Code.LIMIT_EXCEEDED, "Repository references exceed size or count limits.")
            documents.append((relative, reference_oid, reference_size))
        try:
            validate_references(tuple(ReferenceFile(relative, b"inventory") for relative, _, _ in documents[1:]))
        except ValueError:
            raise SkillInstallError(Code.UNSAFE_REPOSITORY, "Repository references contain ambiguous paths.") from None
        total += length + reference_bytes
        if total > MAX_INSTALL_BYTES:
            raise SkillInstallError(Code.LIMIT_EXCEEDED, "Repository skills exceed installation size limits.")
        blobs.append(tuple(documents))
    if not blobs:
        raise SkillInstallError(Code.NO_SKILLS, "Repository contains no supported SKILL.md files.")
    return tuple(blobs)


def _skill_blobs(tree, max_skill_bytes):
    """Compatibility inspection of entry points; repository roots stay opaque."""
    return tuple((documents[0][1], documents[0][2]) for documents in _package_blobs(tree, max_skill_bytes))


def _check_download(root):
    """Bound observed temporary bytes, without following filesystem redirects."""
    from app.execution.windows_filesystem import pinned_parent
    total = 0
    count = 0
    def visit(folder):
        nonlocal total, count
        with pinned_parent(folder / "anchor", CancellationToken()):
            with os.scandir(folder) as entries:
                for entry in entries:
                    count += 1
                    if count > 16384:
                        raise SkillInstallError(Code.DOWNLOAD_LIMIT, "Temporary repository exceeds its file entry limit.")
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:  # Git atomically replaces its own pack/lock files.
                        continue
                    if _redirect(info):
                        raise SkillInstallError(Code.UNSAFE_REPOSITORY, "Temporary repository contains a filesystem redirect.")
                    if stat.S_ISDIR(info.st_mode):
                        visit(Path(entry.path))
                    elif stat.S_ISREG(info.st_mode):
                        total += info.st_size
                        if total > MAX_DOWNLOAD_BYTES:
                            raise SkillInstallError(Code.DOWNLOAD_LIMIT, "Temporary repository exceeds the download size limit.")
                    else:
                        raise SkillInstallError(Code.UNSAFE_REPOSITORY, "Temporary repository contains an unsupported file.")
    visit(root)


def _redirect(info):
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT


@contextmanager
def _workspace():
    from app.execution.windows_filesystem import pinned_parent
    # Native exclusive creation and pinned ancestors keep cleanup inside this
    # operation's owned directory. No repository path is ever extracted here.
    root = Path(os.path.abspath(tempfile.gettempdir())) / ("orsi-skill-git-" + uuid4().hex)
    identity = _create_directory(root)
    try:
        with pinned_parent(root / "anchor", CancellationToken()):
            try:
                yield root
            finally:
                _clean_contents(root)
    finally:
        try:
            from app.execution.windows_filesystem import directory_identity_for_path
            with pinned_parent(root, CancellationToken()):
                if directory_identity_for_path(root) != identity:
                    raise OSError("Temporary directory identity changed.")
                root.rmdir()  # Empty directory only; never follow a replacement.
        except OSError:
            raise SkillInstallError(Code.CLEANUP_FAILED,
                                    "Temporary repository cleanup failed; no skills were published.") from None


def _clean_contents(folder):
    from app.execution.windows_filesystem import pinned_parent
    try:
        with pinned_parent(folder / "anchor", CancellationToken()):
            with os.scandir(folder) as scan:
                children = [Path(entry.path) for entry in scan]
            for child in children:
                info = child.lstat()
                if _redirect(info):
                    raise OSError("Cleanup refuses filesystem redirects.")
                if stat.S_ISDIR(info.st_mode):
                    _clean_contents(child)
                    child.rmdir()
                elif stat.S_ISREG(info.st_mode):
                    _delete_file(child)
                else:
                    raise OSError("Cleanup refuses unsupported files.")
    except OSError:
        raise SkillInstallError(Code.CLEANUP_FAILED,
                                "Temporary repository cleanup failed; no skills were published.") from None


def _delete_file(path):
    """Delete a regular owned file by non-following handle, including Git read-only packs."""
    import ctypes as C
    from ctypes import wintypes as W
    from app.execution.windows_filesystem import _kernel, _FileInformation
    api = _kernel()
    deadline = monotonic() + 5
    while True:
        handle = api.CreateFileW(str(path), 0x10000 | 0x80, 0x1, None, 3, 0x00200000, None)
        if handle != C.c_void_p(-1).value:
            break
        error = C.get_last_error()
        # Kernel teardown can briefly retain handles after all job processes exit.
        # Retry only sharing violations on this owned file, never other errors.
        if error != 32 or monotonic() >= deadline:
            raise C.WinError(error)
        sleep(0.01)
    try:
        info = _FileInformation()
        if not api.GetFileInformationByHandle(handle, C.byref(info)) or info.attributes & (0x10 | 0x400 | 0x4):
            raise OSError("Cleanup requires a non-reparse regular file.")
        api.SetFileInformationByHandle.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]
        api.SetFileInformationByHandle.restype = W.BOOL
        flags = W.DWORD(0x1 | 0x10)  # FILE_DISPOSITION_DELETE | IGNORE_READONLY_ATTRIBUTE
        if not api.SetFileInformationByHandle(handle, 21, C.byref(flags), C.sizeof(flags)):
            raise C.WinError(C.get_last_error())
    finally:
        api.CloseHandle(handle)
