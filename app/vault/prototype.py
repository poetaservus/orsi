"""Disposable phase 1 experiment. Never use for real personal data.

Only immutable objects are implemented. See docs/vault-phase1-contract.md for
the proposed application contract and the deliberately missing production gates.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
from threading import RLock
from typing import BinaryIO
from uuid import UUID, uuid4

from nacl import bindings as sodium
from nacl.exceptions import CryptoError
from nacl.pwhash import argon2id
from nacl.secret import Aead
from nacl.utils import random


FORMAT = "orsi-vault-prototype"
VERSION = 1
CHUNK_BYTES = 1024 * 1024
MAX_OBJECT_BYTES = 512 * CHUNK_BYTES
MAX_HEADER_BYTES = 4096
MAX_METADATA_BYTES = 4096
_STREAM_HEADER = sodium.crypto_secretstream_xchacha20poly1305_HEADERBYTES
_OVERHEAD = sodium.crypto_secretstream_xchacha20poly1305_ABYTES
_MESSAGE = sodium.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE
_FINAL = sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL
_LENGTH = struct.Struct(">I")
_OBJECT_ID = re.compile(r"[0-9a-f]{32}")


class VaultError(Exception):
    """Fixed messages only; callers must not log chained OS/parser exceptions."""


class InvalidVault(VaultError):
    pass


class VaultLocked(VaultError):
    pass


class StorageUnavailable(VaultError):
    pass


class Domain(StrEnum):
    PERSONAL = "personal"
    CREDENTIAL = "credential"


@dataclass(frozen=True)
class KdfCost:
    operations: int = 2
    memory_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        # Bound untrusted header parameters before allocating KDF memory.
        if (type(self.operations) is not int or not 2 <= self.operations <= 6
                or type(self.memory_bytes) is not int
                or not 64 * 1024 * 1024 <= self.memory_bytes <= 256 * 1024 * 1024):
            raise InvalidVault("Unsupported password derivation parameters.")


@dataclass(frozen=True)
class ObjectReference:
    profile_id: str
    object_id: str
    domain: Domain

    def __post_init__(self):
        if (not isinstance(self.object_id, str) or not _OBJECT_ID.fullmatch(self.object_id)
                or not isinstance(self.domain, Domain)):
            raise InvalidVault("Invalid object reference.")
        _profile_id(self.profile_id)


@dataclass(frozen=True)
class StoredObject:
    logical_path: str = field(repr=False)
    content: bytes = field(repr=False)


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidVault("Duplicate vault metadata field.")
        result[key] = value
    return result


def _profile_id(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid profile identifier.")
    return value


def _logical_path(value):
    # An encrypted logical name is never a host filesystem path.
    try:
        size = len(value.encode("utf-8")) if isinstance(value, str) else 0
    except UnicodeError:
        raise InvalidVault("Use a valid relative internal object path.") from None
    if (not isinstance(value, str) or not value or size > 2048
            or "\\" in value or ":" in value or "\0" in value
            or PurePosixPath(value).is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise InvalidVault("Use a relative internal object path.")
    return value


def _ordinary(path):
    # Static alias check for this offline experiment; not a race-safe sandbox.
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise StorageUnavailable("Vault paths must not follow filesystem links.")


def _read_exact(stream, size):
    value = stream.read(size)
    if len(value) != size:
        raise InvalidVault("Vault object is incomplete.")
    return value


def _decode(value, size):
    if not isinstance(value, str):
        raise InvalidVault("Invalid vault header.")
    decoded = base64.b64decode(value, validate=True)
    if len(decoded) != size:
        raise InvalidVault("Invalid vault header.")
    return decoded


def _password(value):
    if not isinstance(value, bytes) or not 1 <= len(value) <= 1024:
        raise VaultError("Supply a nonempty password as bytes, up to 1024 bytes.")
    return value


class VaultPrototype:
    """Single-process synthetic object store. Location is never a key input.

    A lock drops and best-effort overwrites owned key buffers. Python, libsodium
    and the OS can retain other copies; this is not guaranteed memory erasure.
    """

    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        self._keys = None
        self._profile = None
        self._lock = RLock()

    @classmethod
    def create(cls, root: Path, password: bytes, *, synthetic: bool,
               cost: KdfCost = KdfCost()) -> "VaultPrototype":
        if synthetic is not True:
            raise VaultError("The prototype accepts synthetic data only.")
        _password(password)
        if not isinstance(cost, KdfCost):
            raise TypeError("Password derivation requires KdfCost.")
        store = cls(root)
        _ordinary(store.root)
        metadata = {
            "format": FORMAT, "version": VERSION, "profile_id": str(uuid4()),
            "cipher": "xchacha20poly1305-secretstream",
            "kdf": {"name": "argon2id13", "operations": cost.operations,
                    "memory_bytes": cost.memory_bytes,
                    "salt": base64.b64encode(random(argon2id.SALTBYTES)).decode("ascii")},
        }
        keys = random(2 * Aead.KEY_SIZE)
        wrapping_key = store._derive(password, metadata["kdf"])
        wrapped = bytes(Aead(wrapping_key).encrypt(keys, aad=_json(metadata)))
        header = {**metadata, "wrapped_keys": base64.b64encode(wrapped).decode("ascii")}
        # Exclusive creation never adopts or replaces an existing directory.
        try:
            store.root.mkdir(parents=True, exist_ok=False)
            (store.root / "objects").mkdir()
            with (store.root / "header.json").open("xb") as output:
                output.write(_json(header))
                output.flush()
                os.fsync(output.fileno())
        except OSError:
            raise StorageUnavailable("Cannot create a new disposable vault at this location.") from None
        # Failed creation is left for explicit disposal, never treated as usable.
        store._keys = bytearray(keys)
        store._profile = metadata["profile_id"]
        return store

    @property
    def unlocked(self):
        return self._keys is not None

    @property
    def profile_id(self):
        self._require_keys()
        return self._profile

    @staticmethod
    def _derive(password, kdf):
        cost = KdfCost(kdf["operations"], kdf["memory_bytes"])
        return argon2id.kdf(Aead.KEY_SIZE, password, _decode(kdf["salt"], argon2id.SALTBYTES),
                           opslimit=cost.operations, memlimit=cost.memory_bytes)

    def unlock(self, password: bytes):
        with self._lock:
            self.lock()
            _password(password)
            try:
                _ordinary(self.root / "header.json")
                with (self.root / "header.json").open("rb") as source:
                    raw = source.read(MAX_HEADER_BYTES + 1)
                if len(raw) > MAX_HEADER_BYTES:
                    raise InvalidVault("Vault header exceeds its size limit.")
                header = json.loads(raw, object_pairs_hook=_unique_pairs)
                if (not isinstance(header, dict) or set(header) != {
                        "format", "version", "profile_id", "cipher", "kdf", "wrapped_keys"}
                        or header["format"] != FORMAT or type(header["version"]) is not int
                        or header["version"] != VERSION
                        or header["cipher"] != "xchacha20poly1305-secretstream"):
                    raise InvalidVault("Unsupported vault format.")
                profile = _profile_id(header["profile_id"])
                kdf = header["kdf"]
                if (not isinstance(kdf, dict) or set(kdf) != {"name", "operations", "memory_bytes", "salt"}
                        or kdf["name"] != "argon2id13"):
                    raise InvalidVault("Unsupported password derivation format.")
                wrapped = _decode(header.pop("wrapped_keys"), 2 * Aead.KEY_SIZE + Aead.NONCE_SIZE + Aead.MACBYTES)
                keys = Aead(self._derive(password, kdf)).decrypt(wrapped, aad=_json(header))
                self._keys, self._profile = bytearray(keys), profile
            except OSError:
                raise StorageUnavailable("Vault storage is unavailable.") from None
            except (CryptoError, ValueError, TypeError, KeyError):
                raise InvalidVault("Password or vault header authentication failed.") from None

    def lock(self):
        with self._lock:
            if self._keys is not None:
                self._keys[:] = b"\0" * len(self._keys)
            self._keys, self._profile = None, None

    def _require_keys(self):
        if not self.unlocked:
            raise VaultLocked("Unlock the disposable vault first.")

    def _key(self, domain):
        self._require_keys()
        offset = Aead.KEY_SIZE if domain == Domain.CREDENTIAL else 0
        return bytes(self._keys[offset:offset + Aead.KEY_SIZE])

    def _aad(self, reference):
        if reference.profile_id != self._profile:
            raise InvalidVault("Object belongs to a different profile.")
        return _json({"format": FORMAT, "version": VERSION, "profile_id": self._profile,
                      "object_id": reference.object_id, "domain": reference.domain.value})

    def put(self, logical_path: str, source: BinaryIO, *, domain: Domain = Domain.PERSONAL) -> ObjectReference:
        with self._lock:
            self._require_keys()
            logical_path = _logical_path(logical_path)
            metadata = _json({"logical_path": logical_path})
            if len(metadata) > MAX_METADATA_BYTES:
                raise InvalidVault("Internal object metadata exceeds its size limit.")
            reference = ObjectReference(self._profile, uuid4().hex, domain)
            aad, key = self._aad(reference), self._key(domain)
            objects = self.root / "objects"
            pending = objects / (reference.object_id + ".pending")
            try:
                _ordinary(objects)
                state = sodium.crypto_secretstream_xchacha20poly1305_state()
                stream_header = sodium.crypto_secretstream_xchacha20poly1305_init_push(state, key)
                with pending.open("xb") as output:
                    output.write(stream_header)

                    def frame(data, tag):
                        encrypted = sodium.crypto_secretstream_xchacha20poly1305_push(state, data, aad, tag)
                        output.write(_LENGTH.pack(len(encrypted)))
                        output.write(encrypted)

                    frame(metadata, _MESSAGE)
                    total = 0
                    while True:
                        chunk = source.read(CHUNK_BYTES)
                        if not isinstance(chunk, bytes) or len(chunk) > CHUNK_BYTES:
                            raise VaultError("Object sources must provide bounded byte chunks.")
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_OBJECT_BYTES:
                            raise VaultError("Object exceeds the prototype size limit.")
                        frame(chunk, _MESSAGE)
                    frame(b"", _FINAL)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(pending, objects / (reference.object_id + ".bin"))
                return reference
            except (OSError, StorageUnavailable):
                self.lock()
                raise StorageUnavailable("Encrypted object save failed; no fallback was created.") from None
            finally:
                try:
                    pending.unlink(missing_ok=True)
                except OSError:
                    # An encrypted orphan on removed media requires later disposal.
                    pass

    def read(self, reference: ObjectReference) -> StoredObject:
        with self._lock:
            self._require_keys()
            if not isinstance(reference, ObjectReference):
                raise InvalidVault("Invalid object reference.")
            aad, key = self._aad(reference), self._key(reference.domain)
            path = self.root / "objects" / (reference.object_id + ".bin")
            try:
                _ordinary(path)
                with path.open("rb") as source:
                    state = sodium.crypto_secretstream_xchacha20poly1305_state()
                    sodium.crypto_secretstream_xchacha20poly1305_init_pull(state, _read_exact(source, _STREAM_HEADER), key)

                    def frame(limit):
                        size = _LENGTH.unpack(_read_exact(source, _LENGTH.size))[0]
                        if not _OVERHEAD <= size <= limit + _OVERHEAD:
                            raise InvalidVault("Invalid encrypted object frame size.")
                        return sodium.crypto_secretstream_xchacha20poly1305_pull(state, _read_exact(source, size), aad)

                    metadata, tag = frame(MAX_METADATA_BYTES)
                    metadata = json.loads(metadata, object_pairs_hook=_unique_pairs)
                    if tag != _MESSAGE or not isinstance(metadata, dict) or set(metadata) != {"logical_path"}:
                        raise InvalidVault("Invalid encrypted object metadata.")
                    logical_path = _logical_path(metadata["logical_path"])
                    # No partial plaintext is returned before FINAL and EOF verify.
                    with BytesIO() as output:
                        while True:
                            data, tag = frame(CHUNK_BYTES)
                            if tag == _FINAL:
                                if data or source.read(1):
                                    raise InvalidVault("Invalid encrypted object ending.")
                                return StoredObject(logical_path, output.getvalue())
                            if tag != _MESSAGE or not data or output.tell() + len(data) > MAX_OBJECT_BYTES:
                                raise InvalidVault("Invalid encrypted object data.")
                            output.write(data)
            except (OSError, StorageUnavailable):
                self.lock()
                raise StorageUnavailable("Encrypted object storage is unavailable.") from None
            except (CryptoError, ValueError, TypeError, KeyError):
                raise InvalidVault("Encrypted object authentication failed.") from None
