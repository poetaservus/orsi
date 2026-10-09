"""Owned vault files, exclusive process lease and atomic ciphertext publication."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import stat
from uuid import uuid4

from app.runtime.cancellation import CancellationToken
from app.state.atomic import replace_state_file
from app.vault.types import RecoveryRequired, StorageUnavailable, VaultBusy


def ordinary(path):
    path = Path(path).absolute()
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise StorageUnavailable("Vault storage cannot follow filesystem links.")


@contextmanager
def snapshot(path, limit):
    ordinary(path)
    if os.name == "nt":
        from app.execution.windows_filesystem import open_file_snapshot
        with open_file_snapshot(path, limit, CancellationToken()) as (stream, _):
            yield stream
    else:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise RecoveryRequired("Invalid vault file type or size.")
            yield stream


def read_bytes(path, limit):
    try:
        with snapshot(path, limit) as source:
            data = source.read(limit + 1)
    except ValueError:
        raise RecoveryRequired("Vault file exceeds its safe size limit.") from None
    if len(data) > limit:
        raise RecoveryRequired("Vault file exceeds its size limit.")
    return data


def sync_directory(path):
    # Windows file fsync + atomic replacement is the process-crash boundary.
    # Physical power-loss/media durability still needs hardware qualification.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_write(path, data):
    ordinary(path.parent)
    pending = path.parent / (".pending-" + uuid4().hex)
    try:
        with pending.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        replace_state_file(pending, path)
        sync_directory(path.parent)
    finally:
        pending.unlink(missing_ok=True)


def iter_files(root):
    """Bounded non-following walk; inspect directories before descending."""
    todo, seen = [Path(root)], 0
    while todo:
        directory = todo.pop()
        ordinary(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                seen += 1
                if seen > 100_000:
                    raise RecoveryRequired("Vault storage inventory exceeds its safe limit.")
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise StorageUnavailable("Vault storage contains a filesystem link.")
                if stat.S_ISDIR(info.st_mode):
                    todo.append(path)
                elif stat.S_ISREG(info.st_mode):
                    yield path, info.st_size
                else:
                    raise RecoveryRequired("Vault storage contains an unsupported file type.")


def remove_owned_snapshot(path, anchor):
    """Remove only one direct child of the explicitly owned backup directory."""
    path, anchor = Path(path).absolute(), Path(anchor).absolute()
    if path.parent != anchor:
        raise RecoveryRequired("Backup cleanup escaped its owned directory.")
    ordinary(path)
    files = list(iter_files(path))
    for child, _ in files:
        relative = child.relative_to(path)
        if not (relative.as_posix() in {"header.json", "state.bin", ".lease"}
                or len(relative.parts) == 2 and relative.parts[0] == "objects"
                and relative.suffix == ".bin" and len(relative.stem) == 32):
            raise RecoveryRequired("Unexpected backup contents were preserved.")
    for child, _ in files:
        child.unlink()
    for directory in sorted((p for p in path.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        directory.rmdir()
    path.rmdir()


class Lease:
    """OS-owned lock: released on close/process death; stale files are harmless."""
    def __init__(self, root):
        self._stack = ExitStack()
        self._fd = None
        try:
            ordinary(root)
            if not root.is_dir():
                raise StorageUnavailable("Vault location is unavailable.")
            if os.name == "nt":
                from app.execution.windows_filesystem import pinned_parent
                for directory in (root, root / "objects", root / "backups"):
                    self._stack.enter_context(pinned_parent(directory / "guard", CancellationToken()))
            ordinary(root / ".lease")
            self._fd = os.open(root / ".lease", os.O_RDWR | os.O_CREAT, 0o600)
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise StorageUnavailable("Vault lease must be an unshared regular file.")
            if info.st_size == 0:
                os.write(self._fd, b"\0")
            os.lseek(self._fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.close()
            if getattr(error, "winerror", None) in {32, 33} or error.errno in {11, 13}:
                raise VaultBusy("Vault is busy or cannot acquire exclusive access.") from None
            raise StorageUnavailable("Cannot acquire vault storage access.") from None
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._stack.close()
