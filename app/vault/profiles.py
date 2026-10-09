"""Explicit profile selection and controls; public bootstrap contains only a locator."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shutil
from uuid import UUID, uuid4

from app.state.storage import JsonStore
from app.vault import files
from app.vault.session import ProfileSession
from app.vault.types import BackupPolicy, Domain, State, VaultError, VaultLocked


@dataclass(frozen=True)
class ProfileLocator:
    root: Path
    mode: str
    encrypted: bool
    profile_id: str


class PlainProfile:
    encrypted = False

    def __init__(self, root):
        self.root, self.state = Path(root).absolute(), State.UNLOCKED
        files.ordinary(self.root)
        self._lease = files.Lease(self.root, child_directories=())

    def lock(self):
        if self._lease is not None:
            self._lease.close()
            self._lease = None
        self.state = State.LOCKED


class ProfileManager:
    def __init__(self, application_root, *, bootstrap=None):
        self.application_root = Path(application_root).absolute()
        self.bootstrap = JsonStore(bootstrap or self.application_root / "state/profile_locator_v1.json")
        self.locator = None
        self.session = None
        self.known_roots = set()
        self.bootstrap_error = False
        try:
            data = self.bootstrap.load()
            if data is not None:
                if (not isinstance(data, dict) or set(data) != {"version", "location", "relative", "mode", "encrypted", "profile_id"}
                        or data["version"] != 1 or type(data["relative"]) is not bool
                        or type(data["encrypted"]) is not bool or data["mode"] not in {"local", "portable"}
                        or not isinstance(data["location"], str) or not data["location"]):
                    raise ValueError()
                UUID(data["profile_id"])
                root = Path(data["location"])
                if data["relative"]:
                    if root.is_absolute() or ".." in root.parts:
                        raise ValueError()
                    root = self.application_root / root
                elif not root.is_absolute():
                    raise ValueError()
                self.locator = ProfileLocator(root.absolute(), data["mode"], data["encrypted"], data["profile_id"])
                self.known_roots.add(self.locator.root)
        except (OSError, ValueError, TypeError, KeyError):
            # An unreadable selection must never fall back to legacy personal data.
            self.bootstrap_error = True

    @property
    def active(self):
        return self.session is not None and self.session._active and self.session._vault.state == State.UNLOCKED

    @property
    def encrypted(self):
        return self.locator is not None and self.locator.encrypted

    def default_location(self, mode="local"):
        if mode == "portable":
            return self.application_root / "profiles" / uuid4().hex
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "O.R.S.I/profiles" / uuid4().hex

    def _remember(self, locator):
        relative = locator.mode == "portable" and locator.root.is_relative_to(self.application_root)
        location = locator.root.relative_to(self.application_root) if relative else locator.root
        self.bootstrap.save({"version": 1, "location": str(location), "relative": relative,
            "mode": locator.mode, "encrypted": locator.encrypted, "profile_id": locator.profile_id})
        self.locator, self.bootstrap_error = locator, False
        self.known_roots.add(locator.root)

    def lock(self):
        if self.session is not None:
            self.session.lock()
            self.session = None

    def use_legacy(self):
        self.lock()
        self.bootstrap.path.unlink(missing_ok=True)
        self.locator, self.bootstrap_error = None, False

    def renew(self):
        self.require_active()
        self.session = self.session.renew()

    def require_active(self):
        if not self.active:
            raise VaultLocked("Unlock the selected profile to continue.")
        self.session.require_active()
        return self.session._vault

    def vault(self):
        backend = self.require_active()
        if not self.encrypted:
            raise VaultError("This control requires an encrypted profile.")
        return backend

    def create(self, root, *, mode="local", encrypted=True, password=b"", quota_bytes=1024**3,
               credential_policy="ask_each_session"):
        if mode not in {"local", "portable"} or type(encrypted) is not bool:
            raise VaultError("Choose local or portable personal storage.")
        if credential_policy not in {"ask_each_session", "save_encrypted"} or (not encrypted and credential_policy != "ask_each_session"):
            raise VaultError("Saved credentials require an encrypted profile.")
        root = Path(root).absolute()
        self._new_location(root)
        self.lock()
        if encrypted:
            from app.vault.engine import Vault
            backend = Vault.create(root, password, quota_bytes=quota_bytes)
            identity = backend._header["profile_id"]
        else:
            files.ordinary(root)
            root.mkdir(parents=True, exist_ok=False)
            identity = str(uuid4())
            files.atomic_write(root / "profile.json", json.dumps({"version": 1, "profile_id": identity}).encode())
            backend = PlainProfile(root)
        session = ProfileSession(backend, protected_roots=self.known_roots)
        try:
            # Full setup preferences stay inside the selected profile.
            JsonStore(session.storage_path("setup/profile_v1.json")).save({"credential_policy": credential_policy,
                "idle_lock_minutes": 0, "storage_guidance_dismissed": False})
            self._remember(ProfileLocator(root, mode, encrypted, identity))
            self.session = session
        except BaseException:
            session.lock()
            raise
        return session

    def select(self, root, *, mode="local", encrypted=True, password=None, recovery_key=None, _expected_id=None):
        if mode not in {"local", "portable"} or type(encrypted) is not bool:
            raise VaultError("Choose local or portable personal storage.")
        self.lock()
        root = Path(root).absolute()
        if encrypted:
            from app.vault.engine import Vault
            backend = Vault(root)
            if recovery_key is None:
                backend.unlock(password)
            else:
                backend.unlock_with_recovery(recovery_key)
            identity = backend._header["profile_id"]
        else:
            data = json.loads(files.read_bytes(root / "profile.json", 4096))
            if set(data) != {"version", "profile_id"} or data["version"] != 1:
                raise VaultError("Select an O.R.S.I personal profile directory.")
            identity = str(UUID(data["profile_id"]))
            backend = PlainProfile(root)
        try:
            if _expected_id is not None and identity != _expected_id:
                raise VaultError("This location contains a different profile. Select it explicitly.")
            locator = ProfileLocator(root, mode, encrypted, identity)
            self._remember(locator)
            self.session = ProfileSession(backend, protected_roots=self.known_roots)
            if encrypted:
                backend.expire()
                backend.prune_backups()
        except BaseException:
            backend.lock()
            self.session = None
            raise
        return self.session

    def unlock(self, password=None, *, recovery_key=None):
        if self.locator is None:
            raise VaultError("Select a personal profile first.")
        expected = self.locator
        session = self.select(expected.root, mode=expected.mode, encrypted=expected.encrypted,
                              password=password, recovery_key=recovery_key, _expected_id=expected.profile_id)
        return session

    def settings(self):
        self.require_active()
        return JsonStore(self.session.storage_path("setup/profile_v1.json"))

    def configure(self, **changes):
        allowed = {"credential_policy", "idle_lock_minutes", "storage_guidance_dismissed"}
        if set(changes) - allowed:
            raise VaultError("Invalid profile setting.")
        if "idle_lock_minutes" in changes and (type(changes["idle_lock_minutes"]) is not int or not 0 <= changes["idle_lock_minutes"] <= 1440):
            raise VaultError("Choose an idle lock between 0 and 1440 minutes.")
        if "storage_guidance_dismissed" in changes and type(changes["storage_guidance_dismissed"]) is not bool:
            raise VaultError("Invalid storage guidance preference.")
        if "credential_policy" in changes and (changes["credential_policy"] not in {"ask_each_session", "save_encrypted"}
                or not self.encrypted and changes["credential_policy"] != "ask_each_session"):
            raise VaultError("Saved credentials require an encrypted profile.")
        store = self.settings()
        value = store.load({})
        store.save({**value, **changes})

    def guidance(self):
        return self.active and self.encrypted and not self.settings().load({}).get("storage_guidance_dismissed", False)

    def usage(self):
        backend = self.require_active()
        application = sum(size for _, size in files.iter_files(self.application_root / "app")) if (self.application_root / "app").is_dir() else 0
        models = sum(size for _, size in files.iter_files(self.application_root / "models")) if (self.application_root / "models").is_dir() else 0
        runtime = sum(size for _, size in files.iter_files(self.application_root / "runtime")) if (self.application_root / "runtime").is_dir() else 0
        personal = backend.usage_bytes() if self.encrypted else sum(size for _, size in files.iter_files(backend.root))
        return {"application": application + runtime, "models": models, "personal": personal,
            "quota": backend.quota_bytes if self.encrypted else None, "free": shutil.disk_usage(backend.root).free}

    def relocate(self, destination, *, mode):
        source = self.vault()
        if mode not in {"local", "portable"}:
            raise VaultError("Choose local or portable storage for the copy.")
        self._new_location(Path(destination).absolute())
        # Stop every writer before taking the relocation snapshot.
        self.renew()
        destination = source.backup(destination)
        # _snapshot authenticates every copied object before selection changes.
        from app.vault.engine import Vault
        copied = Vault(destination)
        # Renew only after a verified copy; source and its independent backups remain.
        self.lock()
        self._remember(ProfileLocator(destination, mode, True, self.locator.profile_id))
        return copied.root

    def restore(self, source, destination, *, mode, password=None, recovery_key=None):
        if mode not in {"local", "portable"}:
            raise VaultError("Choose local or portable storage for the restored profile.")
        source, destination = Path(source).absolute(), Path(destination).absolute()
        if source.is_relative_to(destination) or destination.is_relative_to(source):
            raise VaultError("Restore to a new independent directory outside the backup.")
        self._new_location(Path(destination).absolute())
        Path(destination).absolute().parent.mkdir(parents=True, exist_ok=True)
        self.lock()
        from app.vault.engine import Vault
        backend = Vault.restore(source, destination, password=password, recovery_key=recovery_key)
        try:
            self._remember(ProfileLocator(backend.root, mode, True, backend._header["profile_id"]))
            self.session = ProfileSession(backend, protected_roots=self.known_roots)
        except BaseException:
            backend.lock()
            raise

    def _new_location(self, root):
        files.ordinary(root)
        if any(root.is_relative_to(known) or known.is_relative_to(root) for known in self.known_roots):
            raise VaultError("Choose a new independent directory outside existing profiles.")

    def maintenance(self):
        vault = self.vault()
        vault.expire()
        vault.prune_backups()
        return vault.cleanup()

    def delete_abandoned_drafts(self, *, owned_ids=()):
        vault = self.vault()
        owned_ids = set(owned_ids)
        paths = []
        for path in vault.list_paths():
            if path.startswith("state/conversation_v1/attachments/") and path.endswith("/metadata.json"):
                retained, expiry = vault.retention(path)
                if retained and expiry is not None and path.split("/")[-2] not in owned_ids:
                    paths.append(path)
        if paths:
            vault.delete(tuple(paths))
        return len(paths)

    def delete_records(self, paths):
        vault = self.vault()
        paths = tuple(paths)
        # Active history/preferences have live consumers; use their normal controls.
        if not paths or any(not p.startswith(("state/conversation_v1/archives/", "imports/", "documents/",
                "templates/", "instructions/", "personality/", "memory/", "drafts/", "indexes/", "context/")) for p in paths):
            raise VaultError("Select saved history, imported material or personal records to delete.")
        vault.delete(paths)


def public_error(error):
    """Fixed UI errors never interpolate source, provider or exception contents."""
    from app.vault.types import InvalidCredentials, RecoveryRequired, StorageUnavailable, QuotaExceeded, VaultBusy
    from app.vault.types import MigrationConflict, OriginalChanged, UnverifiedMigration
    if isinstance(error, MigrationConflict):
        return "Matching records already contain different data. Choose explicit replacement or import fewer categories."
    if isinstance(error, OriginalChanged):
        return "An original or protected copy changed. Prepare the import again; originals were preserved."
    if isinstance(error, UnverifiedMigration):
        return "Migration verification is incomplete. Originals remain; retry the import before choosing cleanup."
    if isinstance(error, FileExistsError):
        return "The destination already exists. Choose a new directory; existing files were preserved."
    if isinstance(error, FileNotFoundError):
        return "The selected profile or source file is missing. Reconnect its location or select it again."
    if isinstance(error, InvalidCredentials):
        return "Could not unlock. Check the password or recovery key and try again."
    if isinstance(error, QuotaExceeded):
        return "The vault is full. Increase its quota or manage saved data, then retry."
    if isinstance(error, StorageUnavailable):
        return "Storage is unavailable, read-only or low on free space. Reconnect or choose a writable location, then retry."
    if isinstance(error, RecoveryRequired):
        return "This profile needs recovery. Preserve it and restore a verified encrypted backup."
    if isinstance(error, VaultBusy):
        return "This profile is open elsewhere. Close the other instance and retry."
    if isinstance(error, VaultLocked):
        return "Unlock the selected profile to continue."
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "Encrypted storage needs the optional vault dependency. Install the application's vault extra and retry."
    return "The operation could not finish safely. Review the selected location and choices, then retry."
