"""Versioned authenticated envelopes and bounded libsodium object streams."""
import base64
from io import BytesIO
import json
import os
import struct
from uuid import UUID

from nacl import bindings as sodium
from nacl.exceptions import CryptoError
from nacl.pwhash import argon2id
from nacl.secret import Aead
from nacl.utils import random

from app.vault.files import snapshot
from app.vault.types import KdfCost, RecoveryRequired, VaultError


FORMAT = "orsi-personal-vault"
VERSION = 1
CHUNK = 1024 * 1024
MAX_OBJECT = 512 * CHUNK
MAX_CATALOG = 16 * CHUNK
_LENGTH = struct.Struct(">I")
_OVERHEAD = sodium.crypto_secretstream_xchacha20poly1305_ABYTES
_MESSAGE = sodium.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE
_FINAL = sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryRequired("Duplicate encrypted storage field.")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, RecursionError):
        raise RecoveryRequired("Invalid encrypted storage metadata.") from None


def b64(data):
    return base64.b64encode(data).decode("ascii")


def unb64(value, size=None):
    try:
        result = base64.b64decode(value, validate=True)
        if size is not None and len(result) != size:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise RecoveryRequired("Invalid encrypted storage encoding.") from None


def identifier(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise RecoveryRequired("Invalid profile identifier.") from None
    return value


def password(value):
    if not isinstance(value, bytes) or not 1 <= len(value) <= 1024:
        raise VaultError("Supply password bytes with a length from 1 to 1024.")
    return value


def kdf_spec(cost):
    return {"name": "argon2id13", "operations": cost.operations, "memory_bytes": cost.memory_bytes,
            "salt": b64(random(argon2id.SALTBYTES))}


def derive(value, spec):
    if not isinstance(spec, dict) or set(spec) != {"name", "operations", "memory_bytes", "salt"} or spec["name"] != "argon2id13":
        raise RecoveryRequired("Unsupported password derivation format.")
    try:
        cost = KdfCost(spec["operations"], spec["memory_bytes"])
    except VaultError:
        raise RecoveryRequired("Unsupported password derivation cost.") from None
    return argon2id.kdf(32, password(value), unb64(spec["salt"], 16),
                       opslimit=cost.operations, memlimit=cost.memory_bytes)


def seal(data, key, context):
    return bytes(Aead(key).encrypt(data, aad=canonical(context)))


def unseal(data, key, context):
    try:
        return Aead(key).decrypt(data, aad=canonical(context))
    except (CryptoError, ValueError, TypeError):
        raise RecoveryRequired("Encrypted storage authentication failed.") from None


def write_object(path, source, key, context, reserve):
    source = BytesIO(source) if isinstance(source, bytes) else source
    state = sodium.crypto_secretstream_xchacha20poly1305_state()
    header = sodium.crypto_secretstream_xchacha20poly1305_init_push(state, key)
    aad, total = canonical(context), 0
    reserve(len(header))
    with path.open("xb") as output:
        output.write(header)
        while True:
            data = source.read(CHUNK)
            if not isinstance(data, bytes) or len(data) > CHUNK:
                raise VaultError("Record source must supply bounded byte chunks.")
            if not data:
                break
            total += len(data)
            if total > MAX_OBJECT:
                raise VaultError("Record exceeds the vault object limit.")
            encrypted = sodium.crypto_secretstream_xchacha20poly1305_push(state, data, aad, _MESSAGE)
            reserve(len(encrypted) + 4)
            output.write(_LENGTH.pack(len(encrypted)))
            output.write(encrypted)
        ending = sodium.crypto_secretstream_xchacha20poly1305_push(state, b"", aad, _FINAL)
        reserve(len(ending) + 4)
        output.write(_LENGTH.pack(len(ending)))
        output.write(ending)
        output.flush()
        os.fsync(output.fileno())
    return total


def read_object(path, key, context, expected_size, *, collect=True):
    aad, total, output = canonical(context), 0, BytesIO() if collect else None
    def exact(source, size):
        data = source.read(size)
        if len(data) != size:
            raise RecoveryRequired("Encrypted object is incomplete.")
        return data
    try:
        with snapshot(path, MAX_OBJECT + 2 * CHUNK) as source:
            state = sodium.crypto_secretstream_xchacha20poly1305_state()
            sodium.crypto_secretstream_xchacha20poly1305_init_pull(state, exact(source, 24), key)
            while True:
                size = _LENGTH.unpack(exact(source, 4))[0]
                if not _OVERHEAD <= size <= CHUNK + _OVERHEAD:
                    raise RecoveryRequired("Invalid encrypted object frame length.")
                data, tag = sodium.crypto_secretstream_xchacha20poly1305_pull(state, exact(source, size), aad)
                if tag == _FINAL:
                    if data or source.read(1) or total != expected_size:
                        raise RecoveryRequired("Invalid encrypted object completion.")
                    return output.getvalue() if collect else None
                total += len(data)
                if tag != _MESSAGE or not data or total > MAX_OBJECT or total > expected_size:
                    raise RecoveryRequired("Invalid encrypted object data.")
                if collect:
                    output.write(data)
    except (CryptoError, ValueError, TypeError):
        raise RecoveryRequired("Encrypted object authentication failed.") from None
    finally:
        if output is not None:
            output.close()
