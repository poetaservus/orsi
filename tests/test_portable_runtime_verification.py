"""The package gate must exercise encryption and preserve existing instance data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.verify_openai_runtime import verify_encrypted_profile


@pytest.fixture
def package_root(tmp_path):
    source = Path(__file__).resolve().parents[1]
    for name in ("pyproject.toml", "requirements.txt", "config/cloud.json"):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    return tmp_path


def test_real_encryption_round_trip_preserves_existing_instance_data(package_root):
    state = package_root / "state"
    state.mkdir()
    sentinel = b"synthetic existing instance selection; do not open or replace"
    (state / "profile_locator_v1.json").write_bytes(sentinel)
    profile = package_root / "profiles" / "existing"
    profile.mkdir(parents=True)
    (profile / "keep.bin").write_bytes(sentinel)

    report = verify_encrypted_profile(package_root)

    assert report["vault_round_trip_passed"] and report["vault_locked_read_denied"]
    assert report["vault_owned_resources_released"] and report["vault_temporary_files_removed"]
    assert (state / "profile_locator_v1.json").read_bytes() == sentinel
    assert (profile / "keep.bin").read_bytes() == sentinel
    assert set(state.iterdir()) == {state / "profile_locator_v1.json"}
    assert "synthetic-package" not in json.dumps(report)


def test_encryption_failure_fails_gate_and_cleans_keys_handles_and_fixture(package_root, monkeypatch):
    from app.vault.engine import Vault
    from app.vault.types import State

    opened = []
    actual_create = Vault.create
    actual_read = Vault.read

    def capture(*args, **kwargs):
        vault = actual_create(*args, **kwargs)
        opened.append((vault, vault._keys))
        return vault

    def wrong_record(vault, path, **kwargs):
        return b"wrong synthetic record" if path == "verification/personal" else actual_read(vault, path, **kwargs)

    monkeypatch.setattr(Vault, "create", capture)
    monkeypatch.setattr(Vault, "read", wrong_record)
    with pytest.raises(RuntimeError, match="did not round trip"):
        verify_encrypted_profile(package_root)
    assert len(opened) == 1
    vault, keys = opened[0]
    assert vault.state == State.LOCKED and vault._keys is None and vault._lease is None
    assert not any(keys)
    assert not list((package_root / "state").iterdir())


@pytest.mark.parametrize("mismatch", ["missing_requirement", "installed_version"])
def test_crypto_dependency_mismatch_fails_before_creating_profile(package_root, monkeypatch, mismatch):
    import nacl

    if mismatch == "missing_requirement":
        requirements = package_root / "requirements.txt"
        requirements.write_text("\n".join(line for line in requirements.read_text().splitlines()
                                          if not line.startswith("PyNaCl==")) + "\n")
    else:
        monkeypatch.setattr(nacl, "__version__", "0.0.0")
    with pytest.raises(RuntimeError, match="does not match the Windows manifest"):
        verify_encrypted_profile(package_root)
    assert not (package_root / "state").exists()


def test_public_package_gate_fails_when_encryption_dependency_is_missing(package_root):
    # A fresh process prevents crypto imports elsewhere in the suite hiding the gap.
    source = """
import importlib.abc, runpy, sys
class MissingCrypto(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'nacl' or fullname.startswith('nacl.'):
            raise ModuleNotFoundError('Synthetic missing encryption dependency', name=fullname)
sys.meta_path.insert(0, MissingCrypto())
runpy.run_module('tools.verify_openai_runtime', run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-c", source], cwd=package_root,
        env=dict(os.environ, OPENAI_API_KEY="synthetic-secret-must-not-be-reported"),
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"passed": False, "error_type": "ModuleNotFoundError"}
    assert "synthetic-secret-must-not-be-reported" not in result.stdout + result.stderr
    assert not (package_root / "state").exists()
