"""Focused phase 2 acceptance: synthetic inputs, both simulated storage modes."""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytest.importorskip("nacl.secret", reason="Install the optional vault extra for engine tests.")

from app.vault import crypto as c
from app.vault import files as f
from app.vault.engine import Vault
from app.vault.types import (
    BackupPolicy, Domain, InvalidCredentials, QuotaExceeded, RecordWrite, RecoveryRequired,
    State, StorageUnavailable, VaultBusy, VaultError, VaultLocked,
)


PASSWORD = b"synthetic-phase2-password"
CHANGED = b"synthetic-phase2-changed-password"
MARKER = b"SYNTHETIC-PHASE2-PERSONAL-MARKER"
SECRET = b"SYNTHETIC-PHASE2-CREDENTIAL-MARKER"


@pytest.fixture(params=("local", "portable"))
def vault(tmp_path, request):
    store = Vault.create(tmp_path / request.param / "vault", PASSWORD)
    yield store
    store.lock()


def reopen(vault, password=PASSWORD):
    vault.lock()
    vault.unlock(password)


def blob(vault, path, domain=Domain.PERSONAL):
    return vault.root / "objects" / (vault._catalog[domain.value][path]["object_id"] + ".bin")


def test_create_reopen_domains_and_locked_key_lifetime(vault):
    profile = vault.profile_id
    vault.put("history/private-title", MARKER)
    vault.put("connections/private-provider", SECRET, domain=Domain.CREDENTIAL)
    assert vault.list_paths() == ("history/private-title",)
    assert vault.read("connections/private-provider", domain=Domain.CREDENTIAL) == SECRET
    assert vault._key() != vault._key(Domain.CREDENTIAL)
    owned = vault._keys
    vault.lock()
    assert not any(owned) and vault.state == State.LOCKED
    for operation in (lambda: vault.read("history/private-title"), vault.list_paths,
                      lambda: vault.put("blocked", MARKER)):
        with pytest.raises(VaultLocked):
            operation()
    with pytest.raises(InvalidCredentials):
        vault.unlock(b"synthetic-wrong-password")
    assert vault.state == State.LOCKED
    vault.unlock(PASSWORD)
    assert vault.profile_id == profile and vault.read("history/private-title") == MARKER


def test_password_rewrap_recovery_rotation_disable_and_no_asset_rewrite(vault):
    vault.put("outputs/image", MARKER)
    original = hashlib.sha256(blob(vault, "outputs/image").read_bytes()).digest()
    recovery = vault.generate_recovery_key()
    assert len(recovery) == 32
    vault.change_password(CHANGED)
    assert hashlib.sha256(blob(vault, "outputs/image").read_bytes()).digest() == original
    vault.lock()
    with pytest.raises(InvalidCredentials):
        vault.unlock(PASSWORD)
    vault.unlock(CHANGED)
    vault.lock()
    with pytest.raises(InvalidCredentials):
        vault.unlock_with_recovery(b"x" * 32)
    vault.unlock_with_recovery(recovery)
    assert vault.read("outputs/image") == MARKER
    replacement = vault.generate_recovery_key()
    vault.lock()
    with pytest.raises(InvalidCredentials):
        vault.unlock_with_recovery(recovery)
    vault.unlock_with_recovery(replacement)
    vault.change_password(PASSWORD)
    vault.disable_recovery()
    vault.lock()
    with pytest.raises(InvalidCredentials):
        vault.unlock_with_recovery(replacement)
    vault.unlock(PASSWORD)
    assert vault.read("outputs/image") == MARKER


@pytest.mark.parametrize("damage", ("object", "truncated", "missing-final", "appended", "frame-size", "catalog", "header", "kdf", "prototype", "oversize-header"))
def test_corruption_is_rejected_without_rewriting_originals(vault, damage):
    vault.put("history/item", MARKER)
    path = blob(vault, "history/item")
    if damage == "catalog":
        path = vault.root / "state.bin"
    elif damage in {"header", "kdf", "prototype", "oversize-header"}:
        path = vault.root / "header.json"
    raw = path.read_bytes()
    if damage == "truncated":
        raw = raw[:-5]
    elif damage == "oversize-header":
        raw = b" " * (16 * 1024 + 1)
    elif damage == "missing-final":
        raw = raw[:-21]
    elif damage == "appended":
        raw += b"synthetic-trailer"
    elif damage == "frame-size":
        raw = raw[:24] + b"\xff" * 4 + raw[28:]
    elif damage in {"header", "kdf", "prototype"}:
        header = json.loads(raw)
        if damage == "header":
            header["recovery"] = {"wrapped_keys": header["password"]["wrapped_keys"]}
        elif damage == "kdf":
            header["password"]["kdf"]["memory_bytes"] = 2**60
        else:
            header["format"] = "orsi-vault-prototype"
        raw = json.dumps(header).encode()
    else:
        raw = raw[:-1] + bytes([raw[-1] ^ 1])
    path.write_bytes(raw)
    vault.lock()
    with pytest.raises(RecoveryRequired):
        vault.unlock(PASSWORD)
    assert vault.state == State.RECOVERY_REQUIRED and vault._keys is None
    assert path.read_bytes() == raw


def test_batch_commit_reference_deletion_shared_assets_and_stale_index_cleanup(vault):
    vault.write_batch((
        RecordWrite("assets/original", MARKER, retained=False),
        RecordWrite("assets/preview", b"synthetic-preview", retained=False),
        RecordWrite("assets/extracted", b"synthetic-extraction", retained=False),
        RecordWrite("indexes/private-index", b"synthetic-index", retained=False),
        RecordWrite("history/one", b"one", ("assets/original", "assets/preview", "assets/extracted", "indexes/private-index")),
        RecordWrite("history/two", b"two", ("assets/original",)),
    ))
    vault.delete(("history/one",))
    assert set(vault.list_paths()) == {"history/two", "assets/original"}
    assert vault.read("assets/original") == MARKER
    for removed in ("history/one", "assets/preview", "assets/extracted", "indexes/private-index"):
        with pytest.raises(VaultError):
            vault.read(removed)
    vault.delete(("history/two",))
    assert vault.list_paths() == () and not list((vault.root / "objects").iterdir())
    reopen(vault)
    assert vault.list_paths() == ()


def test_expiration_hides_data_before_cleanup_and_preserves_other_owners(vault):
    now = int(time.time())
    vault.write_batch((RecordWrite("assets/shared", MARKER, retained=False),
                       RecordWrite("drafts/abandoned", b"draft", ("assets/shared",), expires_at=now - 1),
                       RecordWrite("history/retained", b"retained", ("assets/shared",))))
    assert "drafts/abandoned" not in vault.list_paths()
    with pytest.raises(VaultError):
        vault.read("drafts/abandoned")
    vault.expire(now=now)
    reopen(vault)
    assert set(vault.list_paths()) == {"history/retained", "assets/shared"}


def test_temporary_record_defaults_to_one_day_and_reclaims_its_ciphertext(vault):
    before = int(time.time())
    vault.put_temporary("drafts/recovery-copy", MARKER)
    deadline = vault._catalog["personal"]["drafts/recovery-copy"]["expires_at"]
    assert before + 86400 <= deadline <= int(time.time()) + 86400
    vault.expire(now=deadline)
    assert vault.list_paths() == () and not list((vault.root / "objects").iterdir())


def test_interrupted_catalog_publication_preserves_old_complete_asset_set(vault, monkeypatch):
    vault.write_batch((RecordWrite("asset/original", MARKER, retained=False),
                       RecordWrite("asset/preview", b"old-preview", retained=False),
                       RecordWrite("history/one", b"old", ("asset/original", "asset/preview"))))
    original_atomic = f.atomic_write
    def fail_catalog(path, data):
        if path.name == "state.bin":
            raise OSError("synthetic interrupted commit")
        original_atomic(path, data)
    with monkeypatch.context() as context:
        context.setattr(f, "atomic_write", fail_catalog)
        with pytest.raises(StorageUnavailable):
            vault.write_batch((RecordWrite("asset/original", b"new-original", retained=False),
                               RecordWrite("asset/preview", b"new-preview", retained=False),
                               RecordWrite("history/one", b"new", ("asset/original", "asset/preview"))))
    assert vault.state == State.UNAVAILABLE
    vault.unlock(PASSWORD)
    assert vault.read("history/one") == b"old"
    assert vault.read("asset/original") == MARKER and vault.read("asset/preview") == b"old-preview"
    assert len(list((vault.root / "objects").iterdir())) == 3


def test_error_after_catalog_replacement_preserves_new_committed_blobs(vault, monkeypatch):
    vault.put("history/item", b"old")
    atomic = f.atomic_write
    def committed_then_error(path, data):
        atomic(path, data)
        if path.name == "state.bin":
            raise OSError("synthetic durability reporting failure")
    with monkeypatch.context() as context:
        context.setattr(f, "atomic_write", committed_then_error)
        with pytest.raises(StorageUnavailable):
            vault.put("history/item", MARKER)
    vault.unlock(PASSWORD)
    assert vault.read("history/item") == MARKER


def test_interrupted_deletion_cleanup_never_restores_normal_visibility(vault, monkeypatch):
    vault.put("history/private", MARKER)
    target = blob(vault, "history/private")
    unlink = Path.unlink
    def deny_owned(path, *args, **kwargs):
        if path == target:
            raise PermissionError("synthetic cleanup interruption")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as context:
        context.setattr(Path, "unlink", deny_owned)
        vault.delete(("history/private",))
        assert vault.cleanup_pending and target.exists()
        assert vault.list_paths() == ()
        with pytest.raises(VaultError):
            vault.read("history/private")
    reopen(vault)
    assert not target.exists() and not vault.cleanup_pending


def test_quota_disk_space_readonly_failure_and_owned_usage(vault, monkeypatch):
    vault.put("history/retained", MARKER)
    usage = vault.usage_bytes()
    with pytest.raises(QuotaExceeded):
        vault.set_quota(usage - 1)
    vault.set_quota(usage + 16 * 1024)
    with pytest.raises(QuotaExceeded):
        vault.put("outputs/too-large", b"x" * (32 * 1024))
    assert vault.read("history/retained") == MARKER and "outputs/too-large" not in vault.list_paths()
    expected = sum(size for path, size in f.iter_files(vault.root) if path.name != ".lease")
    assert vault.usage_bytes() == expected
    import app.vault.engine as engine
    normal = engine.shutil.disk_usage(vault.root)
    with monkeypatch.context() as context:
        context.setattr(engine.shutil, "disk_usage", lambda path: normal._replace(free=0))
        with pytest.raises(StorageUnavailable):
            vault.put("outputs/full-disk", MARKER)
    assert vault.state == State.UNAVAILABLE
    vault.unlock(PASSWORD)
    def readonly(path, data):
        raise PermissionError("synthetic read-only storage")
    with monkeypatch.context() as context:
        context.setattr(f, "atomic_write", readonly)
        with pytest.raises(StorageUnavailable):
            vault.change_password(CHANGED)
    vault.unlock(PASSWORD)
    assert vault.read("history/retained") == MARKER


def test_large_image_and_backup_restore_survive_explicit_relocation(vault, tmp_path):
    from app.vault.benchmark import synthetic_png
    image = synthetic_png(2048, 2048)
    assert len(image) > 12 * c.CHUNK
    vault.put("outputs/generated.png", BytesIO(image))
    vault.put("connections/key", SECRET, domain=Domain.CREDENTIAL)
    backup = tmp_path / "independent-backup"
    vault.backup(backup)
    before = vault.usage_bytes()
    managed = vault.backup()
    assert vault.usage_bytes() > before + len(image)
    assert vault.read("outputs/generated.png") == image
    profile = vault.profile_id
    (tmp_path / "reinstalled").mkdir()
    restored = Vault.restore(backup, tmp_path / "reinstalled" / "relocated", password=PASSWORD)
    try:
        assert restored.profile_id == profile
        assert restored.read("outputs/generated.png") == image
        assert restored.read("connections/key", domain=Domain.CREDENTIAL) == SECRET
        assert managed.is_dir() and backup.is_dir()
    finally:
        restored.lock()


def test_managed_backup_count_age_and_independent_old_credentials(vault, tmp_path):
    vault.put("connections/key", SECRET, domain=Domain.CREDENTIAL)
    independent = tmp_path / "independent"
    vault.backup(independent)
    vault.set_backup_policy(BackupPolicy(max_count=2, max_age_seconds=100), now=1000)
    first = vault.backup(now=1000)
    second = vault.backup(now=1010)
    third = vault.backup(now=1020)
    assert not first.exists() and second.exists() and third.exists()
    vault.prune_backups(now=1120)
    assert not second.exists() and not third.exists() and independent.exists()
    vault.delete(("connections/key",), domain=Domain.CREDENTIAL)
    vault.change_password(CHANGED)
    restored = Vault.restore(independent, tmp_path / "restored-old", password=PASSWORD)
    try:
        assert restored.read("connections/key", domain=Domain.CREDENTIAL) == SECRET
    finally:
        restored.lock()
    assert vault.list_paths(domain=Domain.CREDENTIAL) == ()


def test_backup_retention_keeps_newest_when_timestamps_tie(vault):
    vault.set_backup_policy(BackupPolicy(max_count=1), now=1000)
    previous = vault.backup(now=1000)
    newest = vault.backup(now=1000)
    assert newest.is_dir() and not previous.exists()


def test_failed_new_backup_preserves_previous_verified_snapshot(vault, monkeypatch):
    vault.put("history/item", MARKER)
    previous = vault.backup()
    atomic = f.atomic_write
    def fail_snapshot(path, data):
        if path.name == "state.bin" and "backups" in path.parts:
            raise OSError("synthetic interrupted backup")
        atomic(path, data)
    with monkeypatch.context() as context:
        context.setattr(f, "atomic_write", fail_snapshot)
        with pytest.raises(StorageUnavailable):
            vault.backup()
    vault.unlock(PASSWORD)
    assert previous.is_dir() and list((vault.root / "backups").iterdir()) == [previous]
    assert vault.read("history/item") == MARKER


def test_corrupt_backup_rejected_before_restore_destination_is_created(vault, tmp_path):
    vault.put("history/item", MARKER)
    source_name = blob(vault, "history/item").name
    backup = tmp_path / "corrupt-backup"
    vault.backup(backup)
    path = backup / "objects" / source_name
    raw = path.read_bytes()[:-1]
    path.write_bytes(raw)
    destination = tmp_path / "failed-restore"
    with pytest.raises(RecoveryRequired):
        Vault.restore(backup, destination, password=PASSWORD)
    assert not destination.exists() and path.read_bytes() == raw


def test_move_after_lock_releases_handles_and_missing_location_is_unavailable(vault):
    vault.put("history/item", MARKER)
    profile = vault.profile_id
    vault.lock()
    moved = vault.root.with_name("relocated-vault")
    vault.root.rename(moved)
    with pytest.raises(StorageUnavailable):
        vault.unlock(PASSWORD)
    assert vault.state == State.UNAVAILABLE
    relocated = Vault(moved)
    try:
        relocated.unlock(PASSWORD)
        assert relocated.profile_id == profile and relocated.read("history/item") == MARKER
    finally:
        relocated.lock()


def test_restore_with_recovery_and_existing_destination_preserved(vault, tmp_path):
    vault.put("history/item", MARKER)
    recovery = vault.generate_recovery_key()
    backup = tmp_path / "backup"
    vault.backup(backup)
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "original").write_bytes(MARKER)
    with pytest.raises(VaultError):
        Vault.restore(backup, destination, recovery_key=recovery)
    assert (destination / "original").read_bytes() == MARKER
    restored = Vault.restore(backup, tmp_path / "recovered", recovery_key=recovery)
    try:
        restored.change_password(CHANGED)
        reopen(restored, CHANGED)
        assert restored.read("history/item") == MARKER
    finally:
        restored.lock()


def child_code(body):
    import nacl
    dependencies = str(Path(nacl.__file__).resolve().parent.parent)
    return "import sys,os;sys.path.insert(0," + repr(dependencies) + ");" + body


def test_concurrent_process_open_fails_and_lease_releases_on_lock(vault):
    with pytest.raises(VaultBusy):
        Vault(vault.root).unlock(PASSWORD)
    code = child_code("from app.vault.engine import Vault\nfrom app.vault.types import VaultBusy\n"
                      "try:\n Vault(sys.argv[1]).unlock(sys.stdin.buffer.read())\nexcept VaultBusy:\n sys.exit(0)\n"
                      "sys.exit(1)\n")
    process = subprocess.run([sys.executable, "-c", code, str(vault.root)], input=PASSWORD, capture_output=True, timeout=15)
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    vault.lock()
    vault.unlock(PASSWORD)
    vault.put("history/after-release", MARKER)


@pytest.mark.parametrize("after_commit", (False, True))
def test_actual_process_death_recovers_one_complete_catalog_and_releases_lease(vault, after_commit):
    vault.put("history/item", b"old")
    vault.lock()
    code = child_code("from pathlib import Path\nfrom app.vault.engine import Vault\nfrom app.vault import files as f\n"
        "vault=Vault(Path(sys.argv[1]));vault.unlock(sys.stdin.buffer.read());atomic=f.atomic_write\n"
        "def crash(path,data):\n"
        + (" atomic(path,data)\n" if after_commit else "")
        + " if path.name=='state.bin': os._exit(73)\n"
        + ("" if after_commit else " atomic(path,data)\n")
        + "f.atomic_write=crash\nvault.put('history/item',b'new')\n")
    result = subprocess.run([sys.executable, "-c", code, str(vault.root)], input=PASSWORD, capture_output=True, timeout=15)
    assert result.returncode == 73, result.stderr.decode(errors="replace")
    vault.unlock(PASSWORD)
    assert vault.read("history/item") == (b"new" if after_commit else b"old")
    assert len(list((vault.root / "objects").iterdir())) == 1


def test_marker_secrets_names_and_recovery_absent_from_persistence_and_logs(vault, caplog):
    vault.put("history/private-name", MARKER)
    vault.put("connections/private-provider", SECRET, domain=Domain.CREDENTIAL)
    recovery = vault.generate_recovery_key()
    vault.backup()
    values = (PASSWORD, SECRET, MARKER, recovery, b"private-name", b"private-provider")
    vault.lock()  # Scan the exclusive lease byte only after its OS lock closes.
    for path, _ in f.iter_files(vault.root):
        assert all(value not in path.read_bytes() for value in values)
    assert all(value.decode(errors="ignore") not in caplog.text for value in (PASSWORD, SECRET, MARKER))
    vault.unlock(PASSWORD)
    # Even the decrypted personal envelope contains only credential ciphertext.
    personal = c.parse(c.unseal((vault.root / "state.bin").read_bytes(), vault._key(), vault._context("catalog")))
    assert b"private-provider" not in c.canonical(personal)


def test_invalid_batch_and_link_paths_do_not_publish_records(vault):
    for bad in ("../outside", "C:/host", "/absolute", "a\\b"):
        with pytest.raises(VaultError):
            vault.put(bad, MARKER)
    with pytest.raises(VaultError):
        vault.put("orphan", MARKER, retained=False)
    with pytest.raises(VaultError):
        vault.put("unresolved", MARKER, references=("missing",))
    assert vault.list_paths() == ()


def test_unsupported_location_does_not_create_a_lease_file(vault, tmp_path):
    unrelated = tmp_path / "unrelated-folder"
    unrelated.mkdir()
    (unrelated / "objects").mkdir()
    (unrelated / "backups").mkdir()
    header = unrelated / "header.json"
    header.write_bytes(b'{"format":"unsupported"}')
    with pytest.raises(RecoveryRequired):
        Vault(unrelated).unlock(PASSWORD)
    assert not (unrelated / ".lease").exists()
    assert header.read_bytes() == b'{"format":"unsupported"}'


def test_hardlinked_lease_cannot_modify_an_external_file(vault, tmp_path):
    vault.lock()
    lease = vault.root / ".lease"
    lease.unlink()
    outside = tmp_path / "outside-empty-file"
    outside.write_bytes(b"")
    os.link(outside, lease)
    with pytest.raises(StorageUnavailable):
        vault.unlock(PASSWORD)
    assert outside.read_bytes() == b"" and vault.state == State.UNAVAILABLE
