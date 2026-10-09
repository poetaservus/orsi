"""Application storage bound to one unlock, with no filesystem plaintext adapter.

Paths are deliberately not os.PathLike: a consumer needing a native filename
must explicitly support a memory stream instead of accidentally creating a copy.
"""
from contextlib import contextmanager
from io import BytesIO
from pathlib import PurePosixPath
from threading import RLock
from types import SimpleNamespace
from uuid import uuid4
from weakref import WeakSet

from app.vault.types import Domain, State, VaultLocked


class ProfileSession:
    def __init__(self, vault, *, protected_roots=()):
        if vault.state != State.UNLOCKED:
            raise VaultLocked("Unlock the selected profile first.")
        self._vault = vault
        self._gate = RLock()
        self._active = True
        self._closing = False
        self._resources = []
        self._streams = WeakSet()
        self.identity = uuid4().hex
        self._protected_roots = tuple(dict.fromkeys((vault.root, *protected_roots)))

    @property
    def protected_roots(self):
        return self._protected_roots

    def require_active(self):
        if not self._active or self._vault.state != State.UNLOCKED:
            raise VaultLocked("The selected profile session is closed.")

    @contextmanager
    def operation(self):
        with self._gate:
            self.require_active()
            yield self._vault

    def path(self, key):
        return PersonalPath(self, key)

    def register(self, *, stop=lambda: None, drain=lambda: None, clear=lambda: None):
        """Workers must cancel, join and discard cached results at this boundary."""
        with self._gate:
            self.require_active()
            self._resources.append((stop, drain, clear))
            resource = self._resources[-1]
        def unregister():
            with self._gate:
                if resource in self._resources:
                    self._resources.remove(resource)
        return unregister

    def lock(self):
        # Revoke first. Previously constructed paths never bind to a later unlock.
        with self._gate:
            if self._closing:
                raise RuntimeError("Profile shutdown is already in progress.")
            if not self._active and not self._resources:
                return
            self._active = False
            self._closing = True
            resources = tuple(self._resources)
        failed = False
        try:
            for phase in range(2):
                for resource in reversed(resources):
                    try:
                        resource[phase]()
                    except Exception:
                        failed = True
            # Keep private caches owned by an undrained worker until a retry can
            # safely clear them. Its storage authority is already revoked.
            if not failed:
                for resource in reversed(resources):
                    try:
                        resource[2]()
                    except Exception:
                        failed = True
            with self._gate:
                for stream in tuple(self._streams):
                    stream.close()
                self._vault.lock()
                if not failed:
                    self._resources.clear()
        finally:
            self._closing = False
        if failed:
            # Keep callbacks for a retry; a manager cannot open the next profile.
            raise RuntimeError("Profile work could not be fully released; retry closing it.") from None

    def open_bytes(self, data):
        with self._gate:
            self.require_active()
            stream = _SessionStream(self, data)
            self._streams.add(stream)
            return stream


class ProfileSelection:
    """Single owner; switching never migrates or merges personal data."""
    def __init__(self):
        self.current = None
        self._lock = RLock()
        self._roots = set()

    def select(self, unlocked_vault):
        with self._lock:
            if self.current is not None:
                self.current.lock()
            self._roots.add(unlocked_vault.root)
            self.current = ProfileSession(unlocked_vault, protected_roots=self._roots)
            return self.current

    def lock(self):
        with self._lock:
            if self.current is not None:
                self.current.lock()
                self.current = None


def _key(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or value.startswith("/") or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError("Invalid protected record path.")
    return value


class PersonalPath:
    """Small storage interface used by state consumers; never a host filename."""
    def __init__(self, session, key):
        self.session, self.key = session, _key(key)

    def __truediv__(self, child):
        return PersonalPath(self.session, self.key + "/" + _key(str(child)))

    @property
    def name(self):
        return PurePosixPath(self.key).name

    @property
    def parent(self):
        return PersonalPath(self.session, str(PurePosixPath(self.key).parent))

    def __repr__(self):
        return "<protected personal path>"

    def __eq__(self, other):
        return isinstance(other, PersonalPath) and self.session is other.session and self.key == other.key

    def exists(self):
        with self.session.operation() as vault:
            return self.key in vault.list_paths() or any(p.startswith(self.key + "/") for p in vault.list_paths())

    def stat(self):
        with self.session.operation() as vault:
            return SimpleNamespace(st_size=vault.size_bytes(self.key))

    def read_bytes(self, *, limit=None):
        with self.session.operation() as vault:
            if self.key not in vault.list_paths():
                raise FileNotFoundError("Protected record is unavailable.")
            if limit is not None and vault.size_bytes(self.key) > limit:
                raise ValueError("Protected record exceeds the consumer size limit.")
            return vault.read(self.key)

    def read_text(self, encoding="utf-8"):
        return self.read_bytes().decode(encoding)

    def write_bytes(self, value):
        with self.session.operation() as vault:
            vault.put(self.key, value)
        return len(value)

    def unlink(self, missing_ok=False):
        with self.session.operation() as vault:
            if self.key not in vault.list_paths():
                if missing_ok:
                    return
                raise FileNotFoundError("Protected record is unavailable.")
            vault.delete((self.key,))


class _SessionStream(BytesIO):
    def __init__(self, session, data):
        super().__init__(data)
        self._session = session

    def read(self, *args):
        with self._session.operation():
            return super().read(*args)

    def readinto(self, *args):
        with self._session.operation():
            return super().readinto(*args)

    def readline(self, *args):
        with self._session.operation():
            return super().readline(*args)

    def readlines(self, *args):
        with self._session.operation():
            return super().readlines(*args)

    def read1(self, *args):
        return self.read(*args)

    def readinto1(self, *args):
        return self.readinto(*args)

    def __next__(self):
        with self._session.operation():
            return super().__next__()

    def seek(self, *args):
        with self._session.operation():
            return super().seek(*args)

    def getvalue(self):
        with self._session.operation():
            return super().getvalue()

    def getbuffer(self):
        raise TypeError("Protected streams do not expose unrevocable buffers.")

    def write(self, *args):
        raise TypeError("Protected snapshots are read only.")

    def writelines(self, *args):
        raise TypeError("Protected snapshots are read only.")

    def truncate(self, *args):
        raise TypeError("Protected snapshots are read only.")

    def writable(self):
        return False


def preserve_storage_path(path):
    from pathlib import Path
    return path if isinstance(path, PersonalPath) else Path(path)
