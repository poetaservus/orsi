"""Necessary offline acceptance checks for the isolated phase 1 experiment."""
from dataclasses import replace
from io import BytesIO
import json
import shutil
import struct

import pytest

pytest.importorskip("nacl.secret", reason="Install the vault-prototype optional extra for these checks.")

from app.vault.prototype import (
    CHUNK_BYTES, Domain, InvalidVault, KdfCost, ObjectReference,
    StorageUnavailable, VaultError, VaultLocked, VaultPrototype,
)
from app.vault.benchmark import run_experiment, synthetic_png


PASSWORD = b"synthetic-test-password-only"
MARKER = b"synthetic-private-record-marker"


@pytest.fixture
def vault(tmp_path):
    store = VaultPrototype.create(tmp_path / "synthetic-vault", PASSWORD, synthetic=True)
    yield store
    store.lock()


def object_path(vault, reference):
    return vault.root / "objects" / (reference.object_id + ".bin")


@pytest.mark.parametrize("mode", ["local", "portable"])
def test_same_format_roundtrip_reopen_and_explicit_relocation(tmp_path, mode):
    root = tmp_path / mode / "original"
    vault = VaultPrototype.create(root, PASSWORD, synthetic=True)
    reference = vault.put("history/private-title.json", BytesIO(MARKER))
    profile = vault.profile_id
    vault.lock()
    relocated = tmp_path / "different-location" / "restored"
    shutil.copytree(root, relocated)
    restored = VaultPrototype(relocated)
    restored.unlock(PASSWORD)
    try:
        assert restored.profile_id == profile
        record = restored.read(reference)
        assert record.logical_path == "history/private-title.json" and record.content == MARKER
        assert root.is_dir()  # Relocation never deletes the source.
        assert MARKER.decode() not in repr(record)
    finally:
        restored.lock()


def test_locked_access_and_wrong_password_drop_owned_key_buffers(vault):
    reference = vault.put("history/item", BytesIO(MARKER))
    owned_keys = vault._keys
    vault.lock()
    assert not any(owned_keys) and not vault.unlocked
    for operation in (lambda: vault.read(reference), lambda: vault.put("new", BytesIO(MARKER))):
        with pytest.raises(VaultLocked):
            operation()
    with pytest.raises(InvalidVault):
        vault.unlock(b"synthetic-wrong-password")
    assert not vault.unlocked
    vault.unlock(PASSWORD)
    assert vault.read(reference).content == MARKER
    # Re-unlock must not retain the previous usable session after failure.
    with pytest.raises(InvalidVault):
        vault.unlock(b"synthetic-wrong-password")
    assert not vault.unlocked


def test_public_header_and_all_persisted_objects_exclude_private_markers(vault):
    vault.put("preferences/private-name", BytesIO(MARKER))
    vault.put("credentials/private-provider", BytesIO(b"synthetic-api-key"), domain=Domain.CREDENTIAL)
    header = json.loads((vault.root / "header.json").read_bytes())
    assert set(header) == {"format", "version", "profile_id", "cipher", "kdf", "wrapped_keys"}
    assert set(header["kdf"]) == {"name", "salt", "operations", "memory_bytes"}
    for path in vault.root.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert all(value not in raw for value in (PASSWORD, MARKER, b"private-name", b"synthetic-api-key", b"private-provider"))
    assert all(path.suffix == ".bin" for path in (vault.root / "objects").iterdir())


@pytest.mark.parametrize("change", ["profile", "salt", "operations", "cipher", "version", "extra", "duplicate", "oversize"])
def test_untrusted_header_is_bounded_and_authenticated(vault, change):
    path = vault.root / "header.json"
    header = json.loads(path.read_bytes())
    if change == "profile":
        header["profile_id"] = "00000000-0000-4000-8000-000000000000"
    elif change == "salt":
        header["kdf"]["salt"] = "AAAAAAAAAAAAAAAAAAAAAA=="
    elif change == "operations":
        header["kdf"]["operations"] = 3  # Allowed value, but fails authenticated binding.
    elif change in {"cipher", "version"}:
        header[change] = "unsupported"
    elif change == "extra":
        header["private_name"] = "forbidden"
    raw = json.dumps(header).encode()
    if change == "duplicate":
        raw = raw[:-1] + b',"version":1}'
    elif change == "oversize":
        raw = b" " * 4097
    path.write_bytes(raw)
    with pytest.raises(InvalidVault):
        vault.unlock(PASSWORD)
    assert not vault.unlocked


def test_abusive_kdf_cost_rejected_before_derivation(vault, monkeypatch):
    import app.vault.prototype as module
    path = vault.root / "header.json"
    header = json.loads(path.read_bytes())
    header["kdf"]["memory_bytes"] = 2**60
    path.write_text(json.dumps(header), encoding="utf-8")
    monkeypatch.setattr(module.argon2id, "kdf", lambda *a, **k: pytest.fail("Untrusted cost reached KDF"))
    with pytest.raises(InvalidVault):
        vault.unlock(PASSWORD)
    with pytest.raises(InvalidVault):
        KdfCost(operations=True)


def test_domain_and_profile_substitution_cannot_decrypt(vault, tmp_path):
    personal = vault.put("private/item", BytesIO(MARKER))
    credential = vault.put("connections/key", BytesIO(MARKER), domain=Domain.CREDENTIAL)
    assert vault._key(Domain.PERSONAL) != vault._key(Domain.CREDENTIAL)
    assert vault.read(credential).content == MARKER
    with pytest.raises(InvalidVault):
        vault.read(replace(credential, domain=Domain.PERSONAL))
    other = VaultPrototype.create(tmp_path / "other-profile", PASSWORD, synthetic=True)
    try:
        with pytest.raises(InvalidVault):
            other.read(personal)
        # Even a forged reference to this profile cannot authenticate a copied object.
        copied = replace(personal, profile_id=other.profile_id)
        shutil.copyfile(object_path(vault, personal), object_path(other, copied))
        with pytest.raises(InvalidVault):
            other.read(copied)
    finally:
        other.lock()


def frames(raw):
    offset = 24  # libsodium secretstream public header.
    result = []
    while offset < len(raw):
        size = struct.unpack(">I", raw[offset:offset + 4])[0]
        result.append(raw[offset:offset + 4 + size])
        offset += 4 + size
    return raw[:24], result


@pytest.mark.parametrize("damage", ["bitflip", "truncated", "missing-final", "reordered", "duplicated", "appended", "frame-length", "object-swap"])
def test_tampering_and_incomplete_streams_never_return_partial_plaintext(vault, damage):
    reference = vault.put("outputs/private-image", BytesIO(MARKER * (CHUNK_BYTES // len(MARKER) + 50)))
    path = object_path(vault, reference)
    raw = path.read_bytes()
    header, chunks = frames(raw)
    if damage == "bitflip":
        raw = raw[:-2] + bytes([raw[-2] ^ 1]) + raw[-1:]
    elif damage == "truncated":
        raw = raw[:-3]
    elif damage == "missing-final":
        raw = header + b"".join(chunks[:-1])
    elif damage == "reordered":
        chunks[1], chunks[2] = chunks[2], chunks[1]
        raw = header + b"".join(chunks)
    elif damage == "duplicated":
        raw = header + chunks[0] + chunks[1] + b"".join(chunks[1:])
    elif damage == "appended":
        raw += b"unexpected-trailer"
    elif damage == "frame-length":
        raw = header + struct.pack(">I", 2**32 - 1) + raw[28:]
    elif damage == "object-swap":
        other = vault.put("other/item", BytesIO(MARKER))
        raw = object_path(vault, other).read_bytes()
    path.write_bytes(raw)
    with pytest.raises(InvalidVault):
        vault.read(reference)


def test_empty_and_large_valid_image_roundtrip(vault):
    empty = vault.put("drafts/empty", BytesIO(b""))
    assert vault.read(empty).content == b""
    image = synthetic_png(2048, 2048)
    assert len(image) > 12 * CHUNK_BYTES and image.startswith(b"\x89PNG\r\n\x1a\n")
    reference = vault.put("outputs/generated.png", BytesIO(image))
    assert vault.read(reference).content == image


def test_storage_removal_and_failed_publish_have_no_plaintext_fallback(vault, monkeypatch):
    reference = vault.put("history/item", BytesIO(MARKER))
    import app.vault.prototype as module
    def full_disk(*args):
        raise OSError("synthetic disk full")
    with monkeypatch.context() as context:
        context.setattr(module.os, "replace", full_disk)
        with pytest.raises(StorageUnavailable):
            vault.put("outputs/new", BytesIO(MARKER))
    assert not vault.unlocked
    assert sorted((vault.root / "objects").iterdir()) == [object_path(vault, reference)]
    vault.unlock(PASSWORD)
    moved = vault.root.with_name("removed-volume")
    vault.root.rename(moved)  # Also proves ordinary handles were released.
    with pytest.raises(StorageUnavailable):
        vault.read(reference)
    assert not vault.unlocked and not vault.root.exists()


@pytest.mark.parametrize("logical_path", ["../escape", "C:/host", "/absolute", "a\\b", "a//b", "a/./b"])
def test_internal_names_cannot_be_host_paths(vault, logical_path):
    with pytest.raises(InvalidVault):
        vault.put(logical_path, BytesIO(MARKER))
    assert not list((vault.root / "objects").iterdir())


def test_create_requires_synthetic_opt_in_and_preserves_existing_directory(tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    original = root / "user-file"
    original.write_bytes(MARKER)
    with pytest.raises(VaultError):
        VaultPrototype.create(tmp_path / "disallowed", PASSWORD, synthetic=False)
    assert not (tmp_path / "disallowed").exists()
    with pytest.raises(StorageUnavailable):
        VaultPrototype.create(root, PASSWORD, synthetic=True)
    assert original.read_bytes() == MARKER and list(root.iterdir()) == [original]


def test_object_reference_blocks_path_injection(vault):
    with pytest.raises(InvalidVault):
        ObjectReference(vault.profile_id, "../header.json", Domain.PERSONAL)


def test_unicode_metadata_roundtrips_or_rejects_before_unreadable_publication(vault):
    name = "documents/" + "\u65e5" * 400
    reference = vault.put(name, BytesIO(MARKER))
    assert vault.read(reference).logical_path == name
    before = set((vault.root / "objects").iterdir())
    for invalid in ("\u65e5" * 680, "invalid\ud800"):
        with pytest.raises(InvalidVault):
            vault.put(invalid, BytesIO(MARKER))
    assert set((vault.root / "objects").iterdir()) == before


def test_source_size_failure_cleans_staging_without_publishing(vault, monkeypatch):
    import app.vault.prototype as module
    monkeypatch.setattr(module, "MAX_OBJECT_BYTES", 16)
    with pytest.raises(VaultError):
        vault.put("oversize", BytesIO(MARKER))
    assert not list((vault.root / "objects").iterdir())


def test_nonbinary_source_is_not_silently_accepted_as_eof(vault):
    class InvalidSource:
        def read(self, size):
            return None
    with pytest.raises(VaultError):
        vault.put("invalid-source", InvalidSource())
    assert not list((vault.root / "objects").iterdir())


def test_experiment_reports_only_counts_fixed_labels_and_simulated_qualification(tmp_path):
    report = run_experiment(tmp_path / "experiment", image_width=32, image_height=32)
    assert {entry["mode"] for entry in report["locations"]} == {"local", "portable"}
    assert not report["minimum_machine_qualified"] and not report["physical_ssd_qualified"]
    assert all(entry["relocation_verified"] and entry["location_simulated"]
               and not entry["plaintext_marker_found"] for entry in report["locations"])
    raw = json.dumps(report)
    assert str(tmp_path) not in raw and "synthetic-provider" not in raw
    assert len(list((tmp_path / "experiment").glob("report-*.json"))) == 1
