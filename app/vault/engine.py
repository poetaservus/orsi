"""Local/portable vault engine. No startup, feature or UI wiring in phase 2.

Immutable encrypted blobs precede one atomic encrypted catalog replacement.
Only the committed catalog grants access; abandoned ciphertext is reclaimable.
"""
from contextlib import contextmanager
from copy import deepcopy
import hmac
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from threading import RLock
import time
from uuid import uuid4

from nacl.utils import random

from app.vault import crypto as c
from app.vault import files as f
from app.vault.types import (
    BackupPolicy, Domain, InvalidCredentials, KdfCost, QuotaExceeded, RecordWrite,
    RecoveryRequired, State, StorageUnavailable, VaultError, VaultLocked,
)


_ID = re.compile(r"[0-9a-f]{32}")
_PENDING = re.compile(r"\.pending-[0-9a-f]{32}")
_RESERVE = 1024 * 1024
_MAX_HEADER = 16 * 1024


def _path(value):
    try:
        valid = (isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 2048
                 and not PurePosixPath(value).is_absolute()
                 and not any(ch in value for ch in ("\\", ":", "\0"))
                 and all(part not in {"", ".", ".."} for part in value.split("/")))
    except UnicodeError:
        valid = False
    if not valid:
        raise VaultError("Use a valid relative vault record path.")
    return value


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


class Vault:
    def __init__(self, root: Path):
        self.root = Path(os.path.abspath(root))
        self.state = State.LOCKED
        self._mutex = RLock()
        self._lease = None
        self._keys = None
        self._header = None
        self._catalog = None
        self.cleanup_pending = False

    @classmethod
    def create(cls, root, password: bytes, *, quota_bytes=1024**3, cost=KdfCost()):
        c.password(password)
        if not _integer(quota_bytes, 4096) or not isinstance(cost, KdfCost):
            raise VaultError("Invalid vault creation limits.")
        vault = cls(root)
        f.ordinary(vault.root)
        try:
            vault.root.mkdir(parents=True, exist_ok=False)
            (vault.root / "objects").mkdir()
            (vault.root / "backups").mkdir()
            vault._lease = f.Lease(vault.root)
            vault._keys = bytearray(random(64))
            vault._header = {"format": c.FORMAT, "version": c.VERSION, "profile_id": str(uuid4()),
                "cipher": "xchacha20poly1305-secretstream", "password": {}, "recovery": None}
            spec = c.kdf_spec(cost)
            vault._header["password"] = {"kdf": spec, "wrapped_keys": c.b64(c.seal(
                bytes(vault._keys), c.derive(password, spec), vault._wrapper_context("password", spec)))}
            vault._authenticate_header(vault._header)
            vault._catalog = {"schema_version": 1, "revision": 0, "quota_bytes": quota_bytes,
                "personal": {}, "credential": {}, "backups": [], "backup_policy": {"max_count": 3, "max_age_seconds": 30 * 86400}}
            vault.state = State.UNLOCKED
            header = c.canonical(vault._header)
            catalog = vault._encode_catalog(vault._catalog)
            vault._space(len(header) + len(catalog), quota=quota_bytes)
            # Header last: an incomplete creation cannot unlock as a valid vault.
            f.atomic_write(vault.root / "state.bin", catalog)
            f.atomic_write(vault.root / "header.json", header)
            return vault
        except OSError:
            vault._close(State.UNAVAILABLE)
            raise StorageUnavailable("Vault creation failed; existing data was not replaced.") from None
        except BaseException:
            vault.lock()
            raise

    @property
    def profile_id(self):
        self._require()
        return self._header["profile_id"]

    def _context(self, role, **values):
        return {"format": c.FORMAT, "version": c.VERSION, "profile_id": self._header["profile_id"],
                "role": role, **values}

    def _wrapper_context(self, role, spec=None):
        return self._context(role, **({"kdf": spec} if spec is not None else {}))

    def _key(self, domain=Domain.PERSONAL):
        offset = 32 if domain == Domain.CREDENTIAL else 0
        return bytes(self._keys[offset:offset + 32])

    def _authenticate_header(self, header):
        header.pop("auth", None)
        header["auth"] = c.b64(c.seal(b"", self._key(), {"role": "header", "header": header}))

    def _validate_header(self, header):
        if (not isinstance(header, dict) or set(header) != {
                "format", "version", "profile_id", "cipher", "password", "recovery", "auth"}
                or header["format"] != c.FORMAT or type(header["version"]) is not int
                or header["version"] != c.VERSION or header["cipher"] != "xchacha20poly1305-secretstream"):
            raise RecoveryRequired("Unsupported vault format; original storage was preserved.")
        c.identifier(header["profile_id"])
        slot = header["password"]
        if not isinstance(slot, dict) or set(slot) != {"kdf", "wrapped_keys"}:
            raise RecoveryRequired("Invalid password wrapper.")
        spec = slot["kdf"]
        if (not isinstance(spec, dict) or set(spec) != {"name", "operations", "memory_bytes", "salt"}
                or spec["name"] != "argon2id13"):
            raise RecoveryRequired("Unsupported password derivation format.")
        try:
            KdfCost(spec["operations"], spec["memory_bytes"])
        except VaultError:
            raise RecoveryRequired("Unsupported password derivation cost.") from None
        c.unb64(spec["salt"], 16)
        c.unb64(slot["wrapped_keys"], 104)
        recovery = header["recovery"]
        if recovery is not None:
            if not isinstance(recovery, dict) or set(recovery) != {"wrapped_keys"}:
                raise RecoveryRequired("Invalid recovery wrapper.")
            c.unb64(recovery["wrapped_keys"], 104)
        c.unb64(header["auth"], 40)

    def unlock(self, password: bytes):
        c.password(password)
        self._unlock(password=password)

    def unlock_with_recovery(self, recovery_key: bytes):
        if not isinstance(recovery_key, bytes) or len(recovery_key) != 32:
            raise InvalidCredentials("Invalid recovery key.")
        self._unlock(recovery_key=recovery_key)

    def _unlock(self, *, password=None, recovery_key=None):
        with self._mutex:
            self.lock()
            try:
                # Selection of an unrelated/unsupported directory must not create
                # a lease file there. Re-read under the lease before trusting it.
                self._validate_header(c.parse(f.read_bytes(self.root / "header.json", _MAX_HEADER)))
                self._lease = f.Lease(self.root)
                header = c.parse(f.read_bytes(self.root / "header.json", _MAX_HEADER))
                self._validate_header(header)
                self._header = header
                role = "password" if password is not None else "recovery"
                slot = header[role]
                if slot is None:
                    raise InvalidCredentials("Recovery is not enabled for this vault.")
                spec = slot["kdf"] if role == "password" else None
                key = c.derive(password, spec) if role == "password" else recovery_key
                try:
                    keys = c.unseal(c.unb64(slot["wrapped_keys"], 104), key, self._wrapper_context(role, spec))
                except RecoveryRequired:
                    raise InvalidCredentials("Password, recovery key or wrapper authentication failed.") from None
                self._keys = bytearray(keys)
                metadata = {k: v for k, v in header.items() if k != "auth"}
                if c.unseal(c.unb64(header["auth"], 40), self._key(), {"role": "header", "header": metadata}) != b"":
                    raise RecoveryRequired("Invalid authenticated vault header.")
                self._catalog = self._decode_catalog(f.read_bytes(self.root / "state.bin", c.MAX_CATALOG + 40))
                self._verify_objects(self.root, self._catalog)
                self.state = State.UNLOCKED
                self._cleanup()
            except (OSError, StorageUnavailable):
                self._close(State.UNAVAILABLE)
                raise StorageUnavailable("Vault storage is unavailable or unreadable.") from None
            except RecoveryRequired:
                self._close(State.RECOVERY_REQUIRED)
                raise
            except BaseException:
                self.lock()
                raise

    def _close(self, state):
        if self._keys is not None:
            self._keys[:] = b"\0" * len(self._keys)
        self._keys = self._header = self._catalog = None
        if self._lease is not None:
            self._lease.close()
            self._lease = None
        self.state = state

    def lock(self):
        with self._mutex:
            self.state = State.LOCKING
            self._close(State.LOCKED)

    def __enter__(self):
        self._require()
        return self

    def __exit__(self, *args):
        self.lock()

    def _require(self):
        if self.state != State.UNLOCKED or self._keys is None:
            raise VaultLocked("Unlock the vault before accessing protected data.")

    @contextmanager
    def _operation(self):
        with self._mutex:
            self._require()
            try:
                yield
            except (OSError, StorageUnavailable):
                self._close(State.UNAVAILABLE)
                raise StorageUnavailable("Vault storage failed; no plaintext fallback was created.") from None
            except RecoveryRequired:
                self._close(State.RECOVERY_REQUIRED)
                raise

    def _encode_catalog(self, catalog):
        encoded = deepcopy(catalog)
        # Personal catalog decryption does not expose credential names/relations.
        encoded["credential"] = c.b64(c.seal(c.canonical(catalog["credential"]), self._key(Domain.CREDENTIAL),
                                            self._context("credential-catalog")))
        data = c.canonical(encoded)
        if len(data) > c.MAX_CATALOG:
            raise VaultError("Vault catalog exceeds its safe size limit.")
        return c.seal(data, self._key(), self._context("catalog"))

    def _decode_catalog(self, raw):
        catalog = c.parse(c.unseal(raw, self._key(), self._context("catalog")))
        if not isinstance(catalog, dict) or set(catalog) != {
                "schema_version", "revision", "quota_bytes", "personal", "credential", "backups", "backup_policy"}:
            raise RecoveryRequired("Invalid vault catalog schema.")
        catalog["credential"] = c.parse(c.unseal(c.unb64(catalog["credential"]), self._key(Domain.CREDENTIAL),
                                                 self._context("credential-catalog")))
        self._validate_catalog(catalog)
        return catalog

    def _validate_catalog(self, catalog):
        if (type(catalog["schema_version"]) is not int or catalog["schema_version"] != 1
                or not _integer(catalog["revision"]) or not _integer(catalog["quota_bytes"], 4096)):
            raise RecoveryRequired("Invalid vault catalog limits.")
        try:
            policy = catalog["backup_policy"]
            if not isinstance(policy, dict) or set(policy) != {"max_count", "max_age_seconds"}:
                raise ValueError()
            BackupPolicy(**policy)
            for domain in Domain:
                records = catalog[domain.value]
                if not isinstance(records, dict) or len(records) > 10_000:
                    raise ValueError()
                ids = set()
                for path, entry in records.items():
                    _path(path)
                    if (not isinstance(entry, dict) or set(entry) != {"object_id", "size", "references", "retained", "expires_at"}
                            or not isinstance(entry["object_id"], str) or not _ID.fullmatch(entry["object_id"])
                            or entry["object_id"] in ids or not _integer(entry["size"]) or entry["size"] > c.MAX_OBJECT
                            or type(entry["retained"]) is not bool or not isinstance(entry["references"], list)
                            or len(entry["references"]) > 1024
                            or entry["expires_at"] is not None and not _integer(entry["expires_at"])):
                        raise ValueError()
                    ids.add(entry["object_id"])
                    for link in entry["references"]:
                        _path(link)
                        if link not in records:
                            raise ValueError()
            backups = catalog["backups"]
            if not isinstance(backups, list) or len(backups) > 101:
                raise ValueError()
            ids = set()
            for backup in backups:
                if (not isinstance(backup, dict) or set(backup) != {"id", "created_at"}
                        or not isinstance(backup["id"], str) or not _ID.fullmatch(backup["id"])
                        or backup["id"] in ids or not _integer(backup["created_at"])):
                    raise ValueError()
                ids.add(backup["id"])
        except (ValueError, TypeError, KeyError, VaultError):
            raise RecoveryRequired("Invalid authenticated vault catalog.") from None

    def _blob_context(self, object_id, domain):
        return self._context("object", object_id=object_id, domain=domain.value)

    def _verify_objects(self, root, catalog):
        for domain in Domain:
            for entry in catalog[domain.value].values():
                c.read_object(root / "objects" / (entry["object_id"] + ".bin"), self._key(domain),
                              self._blob_context(entry["object_id"], domain), entry["size"], collect=False)

    def _usage(self):
        return sum(size for path, size in f.iter_files(self.root) if path != self.root / ".lease")

    def usage_bytes(self):
        with self._operation():
            return self._usage()

    @property
    def quota_bytes(self):
        self._require()
        return self._catalog["quota_bytes"]

    def _space(self, additional, *, quota=None, base_usage=None, disk_additional=None):
        quota = self._catalog["quota_bytes"] if quota is None else quota
        usage = self._usage() if base_usage is None else base_usage
        if usage + additional > quota:
            raise QuotaExceeded("Vault quota cannot accommodate this write and its encrypted staging.")
        if shutil.disk_usage(self.root).free < (additional if disk_additional is None else disk_additional) + _RESERVE:
            raise StorageUnavailable("Insufficient disk space for a safe encrypted write.")

    def _commit(self, catalog):
        catalog = deepcopy(catalog)
        catalog["revision"] += 1
        self._validate_catalog(catalog)
        data = self._encode_catalog(catalog)
        self._space(len(data), quota=catalog["quota_bytes"])
        f.atomic_write(self.root / "state.bin", data)
        self._catalog = catalog

    @staticmethod
    def _prune(records, *, remove=(), now=None):
        removed = set(remove)
        if now is not None:
            removed.update(path for path, entry in records.items()
                           if entry["expires_at"] is not None and entry["expires_at"] <= now)
        records = {path: deepcopy(entry) for path, entry in records.items() if path not in removed}
        for entry in records.values():
            entry["references"] = [link for link in entry["references"] if link not in removed]
        alive, todo = set(), [path for path, entry in records.items() if entry["retained"]]
        while todo:
            path = todo.pop()
            if path in alive:
                continue
            if path not in records:
                raise VaultError("Record references must resolve within their selected store.")
            alive.add(path)
            todo.extend(records[path]["references"])
        return {path: entry for path, entry in records.items() if path in alive}

    def write_batch(self, writes, *, delete=(), domain=Domain.PERSONAL):
        with self._operation():
            self._cleanup()
            if not isinstance(domain, Domain):
                raise VaultError("Select an explicit vault data domain.")
            writes, delete = tuple(writes), tuple(_path(path) for path in delete)
            names = set()
            for write in writes:
                if not isinstance(write, RecordWrite) or write.path in names or write.path in delete:
                    raise VaultError("Invalid or duplicate batch record.")
                _path(write.path)
                names.add(write.path)
                if (type(write.retained) is not bool or not isinstance(write.references, tuple)
                        or len(write.references) > 1024
                        or write.expires_at is not None and not _integer(write.expires_at)):
                    raise VaultError("Invalid record ownership or expiration.")
                for link in write.references:
                    _path(link)
            catalog = deepcopy(self._catalog)
            records = catalog[domain.value]
            for write in writes:
                records[write.path] = {"object_id": uuid4().hex, "size": 0, "references": list(write.references),
                                       "retained": write.retained, "expires_at": write.expires_at}
            # Validate links even in unretained inputs; do not silently adopt orphans.
            for entry in records.values():
                if any(link not in records and link not in delete for link in entry["references"]):
                    raise VaultError("Batch contains an unresolved record reference.")
            catalog[domain.value] = self._prune(records, remove=delete)
            if any(write.path not in catalog[domain.value] for write in writes):
                raise VaultError("Every new asset must have a retained owner in this batch.")
            # Reserve a conservative catalog bound while streaming source bytes.
            metadata_reserve = len(self._encode_catalog(catalog)) + 1024 * len(writes)
            created, committed = [], False
            try:
                for write in writes:
                    entry = records[write.path]
                    pending = self.root / "objects" / (entry["object_id"] + ".pending")
                    final = pending.with_suffix(".bin")
                    created.extend((pending, final))
                    base, reserved = self._usage(), 0
                    def reserve(size):
                        nonlocal reserved
                        reserved += size
                        self._space(reserved + metadata_reserve, base_usage=base,
                                    disk_additional=size + metadata_reserve)
                    entry["size"] = c.write_object(pending, write.source, self._key(domain),
                                                  self._blob_context(entry["object_id"], domain), reserve)
                    # _prune copies entries; propagate the authenticated actual size.
                    catalog[domain.value][write.path]["size"] = entry["size"]
                    f.replace_state_file(pending, final)
                    f.sync_directory(final.parent)
                self._commit(catalog)
                committed = True
            finally:
                if not committed:
                    for path in created:
                        # A replacement can succeed before its durability check
                        # raises. Keep final blobs until reopened catalog decides
                        # ownership; deleting them here could corrupt a commit.
                        if path.suffix != ".pending":
                            continue
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass
            self._cleanup()

    def put(self, path, source, *, references=(), retained=True, expires_at=None, domain=Domain.PERSONAL):
        self.write_batch((RecordWrite(path, source, references, retained, expires_at),), domain=domain)

    def put_temporary(self, path, source, *, references=(), lifetime_seconds=86400, domain=Domain.PERSONAL):
        """Default lifetime for deliberately persisted caches/drafts/recovery copies.

        Unknown tool outcomes must instead use retained records until acknowledged.
        """
        if not _integer(lifetime_seconds, 1) or lifetime_seconds > 30 * 86400:
            raise VaultError("Temporary record lifetime must be between one second and thirty days.")
        self.put(path, source, references=references, expires_at=int(time.time()) + lifetime_seconds, domain=domain)

    def read(self, path, *, domain=Domain.PERSONAL):
        with self._operation():
            if not isinstance(domain, Domain):
                raise VaultError("Select an explicit vault data domain.")
            records = self._prune(self._catalog[domain.value], now=int(time.time()))
            entry = records.get(_path(path))
            if entry is None:
                raise VaultError("Vault record is unavailable or expired.")
            return c.read_object(self.root / "objects" / (entry["object_id"] + ".bin"), self._key(domain),
                                 self._blob_context(entry["object_id"], domain), entry["size"])

    def list_paths(self, *, domain=Domain.PERSONAL):
        with self._operation():
            if not isinstance(domain, Domain):
                raise VaultError("Select an explicit vault data domain.")
            return tuple(sorted(self._prune(self._catalog[domain.value], now=int(time.time()))))

    def delete(self, paths, *, domain=Domain.PERSONAL):
        self.write_batch((), delete=paths, domain=domain)

    def expire(self, *, now=None):
        with self._operation():
            now = int(time.time()) if now is None else now
            if not _integer(now):
                raise VaultError("Invalid retention clock.")
            catalog = deepcopy(self._catalog)
            for domain in Domain:
                catalog[domain.value] = self._prune(catalog[domain.value], now=now)
            if catalog != self._catalog:
                self._commit(catalog)
            self._cleanup()

    def set_quota(self, quota_bytes):
        with self._operation():
            if not _integer(quota_bytes, 4096) or quota_bytes < self._usage():
                raise QuotaExceeded("Quota must cover current encrypted usage.")
            catalog = deepcopy(self._catalog)
            catalog["quota_bytes"] = quota_bytes
            self._commit(catalog)

    def _write_header(self, header):
        self._authenticate_header(header)
        data = c.canonical(header)
        self._space(len(data))
        f.atomic_write(self.root / "header.json", data)
        self._header = header

    def change_password(self, new_password, *, cost=None):
        c.password(new_password)
        with self._operation():
            old = self._header["password"]["kdf"]
            cost = KdfCost(old["operations"], old["memory_bytes"]) if cost is None else cost
            if not isinstance(cost, KdfCost):
                raise VaultError("Invalid password derivation policy.")
            header, spec = deepcopy(self._header), c.kdf_spec(cost)
            header["password"] = {"kdf": spec, "wrapped_keys": c.b64(c.seal(
                bytes(self._keys), c.derive(new_password, spec), self._wrapper_context("password", spec)))}
            self._write_header(header)

    def generate_recovery_key(self):
        """Explicit operation: return a new 32-byte secret once; retain only its wrapper."""
        with self._operation():
            key, header = random(32), deepcopy(self._header)
            header["recovery"] = {"wrapped_keys": c.b64(c.seal(bytes(self._keys), key, self._wrapper_context("recovery")))}
            self._write_header(header)
            return key

    def disable_recovery(self):
        with self._operation():
            header = deepcopy(self._header)
            header["recovery"] = None
            self._write_header(header)

    def _cleanup(self):
        self.cleanup_pending = False
        live = {entry["object_id"] for domain in Domain for entry in self._catalog[domain.value].values()}
        for path in (self.root / "objects").iterdir():
            f.ordinary(path)
            if path.suffix not in {".bin", ".pending"} or not _ID.fullmatch(path.stem) or not path.is_file():
                raise RecoveryRequired("Unexpected object storage entry was preserved.")
            if path.suffix == ".pending" or path.stem not in live:
                try:
                    path.unlink()
                except OSError:
                    self.cleanup_pending = True
        for path in self.root.iterdir():
            if _PENDING.fullmatch(path.name) and path.is_file():
                f.ordinary(path)
                try:
                    path.unlink()
                except OSError:
                    self.cleanup_pending = True
            elif path.name not in {"header.json", "state.bin", ".lease", "objects", "backups"}:
                raise RecoveryRequired("Unexpected vault root entry was preserved.")
        keep = {entry["id"] for entry in self._catalog["backups"]}
        for path in (self.root / "backups").iterdir():
            f.ordinary(path)
            if not (_ID.fullmatch(path.name) or _PENDING.fullmatch(path.name)) or not path.is_dir():
                raise RecoveryRequired("Unexpected backup storage entry was preserved.")
            if path.name not in keep:
                try:
                    f.remove_owned_snapshot(path, self.root / "backups")
                except OSError:
                    self.cleanup_pending = True

    def cleanup(self):
        with self._operation():
            self._cleanup()
            return not self.cleanup_pending

    def _snapshot(self, destination):
        """Create/verify an exclusive ciphertext copy without copying backups recursively."""
        destination = Path(os.path.abspath(destination))
        f.ordinary(destination)
        if destination.exists():
            raise VaultError("Backup destination must be a new directory.")
        catalog = deepcopy(self._catalog)
        catalog["backups"] = []
        encoded = self._encode_catalog(catalog)
        total = len(c.canonical(self._header)) + len(encoded)
        total += sum((self.root / "objects" / (entry["object_id"] + ".bin")).stat().st_size
                     for domain in Domain for entry in catalog[domain.value].values())
        parent = destination.parent
        if not parent.is_dir():
            raise VaultError("Backup parent location must already exist.")
        if shutil.disk_usage(parent).free < total + _RESERVE:
            raise StorageUnavailable("Backup storage has insufficient safe write space.")
        destination.mkdir()
        (destination / "objects").mkdir()
        (destination / "backups").mkdir()
        for domain in Domain:
            for entry in catalog[domain.value].values():
                name = entry["object_id"] + ".bin"
                with f.snapshot(self.root / "objects" / name, c.MAX_OBJECT + 2 * c.CHUNK) as source:
                    with (destination / "objects" / name).open("xb") as output:
                        shutil.copyfileobj(source, output, length=c.CHUNK)
                        output.flush()
                        f.os.fsync(output.fileno())
        f.atomic_write(destination / "state.bin", encoded)
        f.atomic_write(destination / "header.json", c.canonical(self._header))
        if not hmac.compare_digest(f.read_bytes(destination / "header.json", _MAX_HEADER), c.canonical(self._header)):
            raise RecoveryRequired("Copied backup header verification failed.")
        verified = self._decode_catalog(f.read_bytes(destination / "state.bin", c.MAX_CATALOG + 40))
        self._verify_objects(destination, verified)
        f.sync_directory(destination)

    def backup(self, destination=None, *, now=None):
        with self._operation():
            now = int(time.time()) if now is None else now
            if not _integer(now):
                raise VaultError("Invalid backup retention clock.")
            if destination is not None:
                destination = Path(os.path.abspath(destination))
                if destination.is_relative_to(self.root) or self.root.is_relative_to(destination):
                    raise VaultError("Independent backup must use a separate location.")
                self._snapshot(destination)
                return destination
            if self._catalog["backup_policy"]["max_count"] == 0:
                raise VaultError("Managed backups are disabled by their retention policy.")
            backup_id = uuid4().hex
            folder = self.root / "backups"
            pending, final = folder / (".pending-" + backup_id), folder / backup_id
            # Conservative snapshot/copy and catalog allowance; includes old backups.
            live_size = sum((self.root / "objects" / (entry["object_id"] + ".bin")).stat().st_size
                            for domain in Domain for entry in self._catalog[domain.value].values())
            self._space(live_size + 2 * len(self._encode_catalog(self._catalog)) + _MAX_HEADER)
            self._snapshot(pending)
            f.replace_state_file(pending, final)
            f.sync_directory(folder)
            catalog = deepcopy(self._catalog)
            catalog["backups"].append({"id": backup_id, "created_at": now})
            catalog["backups"] = self._retained_backups(catalog, now)
            self._commit(catalog)
            self._cleanup()
            return final

    @staticmethod
    def _retained_backups(catalog, now):
        policy = catalog["backup_policy"]
        backups = [entry for entry in catalog["backups"] if policy["max_age_seconds"] == 0
                   or entry["created_at"] > now - policy["max_age_seconds"]]
        # Append order breaks equal-second ties in favor of the newly verified copy.
        return sorted(reversed(backups), key=lambda entry: entry["created_at"], reverse=True)[:policy["max_count"]]

    def set_backup_policy(self, policy: BackupPolicy, *, now=None):
        if not isinstance(policy, BackupPolicy):
            raise VaultError("Use an explicit managed backup retention policy.")
        with self._operation():
            now = int(time.time()) if now is None else now
            if not _integer(now):
                raise VaultError("Invalid backup retention clock.")
            catalog = deepcopy(self._catalog)
            catalog["backup_policy"] = {"max_count": policy.max_count, "max_age_seconds": policy.max_age_seconds}
            catalog["backups"] = self._retained_backups(catalog, now)
            self._commit(catalog)
            self._cleanup()

    def prune_backups(self, *, now=None):
        self._require()
        self.set_backup_policy(BackupPolicy(**self._catalog["backup_policy"]), now=now)

    @classmethod
    def restore(cls, source, destination, *, password=None, recovery_key=None):
        if (password is None) == (recovery_key is None):
            raise VaultError("Select exactly one restore unlock method.")
        original = cls(source)
        restored = cls(destination)
        try:
            if password is not None:
                original.unlock(password)
            else:
                original.unlock_with_recovery(recovery_key)
            original.backup(destination)
            original.lock()
            if password is not None:
                restored.unlock(password)
            else:
                restored.unlock_with_recovery(recovery_key)
            return restored
        except BaseException:
            restored.lock()
            raise
        finally:
            original.lock()
