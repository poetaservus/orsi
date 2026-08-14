from __future__ import annotations

import os
from pathlib import Path

import pytest

import app.capabilities.host_access as host_access
from app.capabilities.contracts import CapabilityErrorCode, CapabilityExecutionError
from app.capabilities.host_access import (
    CLOUD_FILE_CONTENT_WARNING,
    FULL_LOCAL_READ_WARNING,
    HostAccessPolicy,
    HostReadScope,
    WindowsDriveType,
)


def test_disclosures_describe_host_and_cloud_authority_boundaries():
    local = FULL_LOCAL_READ_WARNING.casefold()
    cloud = CLOUD_FILE_CONTENT_WARNING.casefold()

    assert "current windows account" in local
    assert "does not grant write, delete, execute" in local
    assert "administrator" in local
    assert "network" in local and "background-indexing" in local
    assert "requested host-file content" in cloud
    assert "selected provider" in cloud
    assert "confidential" in cloud


def test_portable_policy_preserves_phase8_root_boundary(tmp_path: Path):
    application_root = tmp_path / "portable"
    application_root.mkdir()
    target = application_root / "inside.txt"
    target.write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    policy = HostAccessPolicy.portable_root(application_root)

    assert policy.read_scope == HostReadScope.PORTABLE_ROOT
    assert policy.resolve_read("inside.txt").resolved == target.resolve()
    with pytest.raises(CapabilityExecutionError) as raised:
        policy.resolve_read(str(outside))
    assert raised.value.code == CapabilityErrorCode.PERMISSION_DENIED


def test_full_local_policy_requires_explicit_acknowledgement(tmp_path: Path):
    if os.name != "nt":
        pytest.skip("Full local read preparation is Windows-specific.")
    application_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    application_root.mkdir()
    user_home.mkdir()

    with pytest.raises(ValueError, match="explicit acknowledgement"):
        HostAccessPolicy.full_local(
            application_root=application_root,
            user_home=user_home,
            acknowledged=False,
        )


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_full_local_policy_reads_outside_application_root_and_uses_user_home(
    tmp_path: Path,
):
    application_root = tmp_path / "portable"
    user_home = tmp_path / "host-user"
    application_root.mkdir()
    user_home.mkdir()
    outside = tmp_path / "host-project" / "sample.txt"
    outside.parent.mkdir()
    outside.write_text("host", encoding="utf-8")
    relative = user_home / "Documents" / "notes.txt"
    relative.parent.mkdir()
    relative.write_text("notes", encoding="utf-8")
    policy = HostAccessPolicy.full_local(
        application_root=application_root,
        user_home=user_home,
        acknowledged=True,
    )

    assert policy.read_scope == HostReadScope.FULL_LOCAL
    assert policy.resolve_read(str(outside)).resolved == outside.resolve()
    assert policy.resolve_read(r"Documents\notes.txt").resolved == relative.resolve()
    assert not str(outside.resolve()).startswith(str(application_root.resolve()))


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
@pytest.mark.parametrize(
    "raw_path",
    [
        r"\\server\share\file.txt",
        r"\\.\pipe\orsi",
        r"\\.\PhysicalDrive0",
        r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\file.txt",
        r"\\?\C:\Windows\System32\config\SAM",
        r"\??\C:\Windows\file.txt",
    ],
)
def test_full_local_policy_rejects_network_and_device_namespaces(
    tmp_path: Path,
    raw_path: str,
):
    application_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    application_root.mkdir()
    user_home.mkdir()
    policy = HostAccessPolicy.full_local(
        application_root=application_root,
        user_home=user_home,
        acknowledged=True,
    )

    with pytest.raises(CapabilityExecutionError) as raised:
        policy.resolve_read(raw_path)
    assert raised.value.code == CapabilityErrorCode.PERMISSION_DENIED


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_full_local_policy_rejects_ambiguous_drive_relative_path(tmp_path: Path):
    application_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    application_root.mkdir()
    user_home.mkdir()
    policy = HostAccessPolicy.full_local(
        application_root=application_root,
        user_home=user_home,
        acknowledged=True,
    )

    with pytest.raises(CapabilityExecutionError) as raised:
        policy.resolve_read(r"C:Windows\system.ini")
    assert raised.value.code == CapabilityErrorCode.INVALID_ARGUMENTS

    with pytest.raises(CapabilityExecutionError) as root_relative:
        policy.resolve_read(r"\Windows\system.ini")
    assert root_relative.value.code == CapabilityErrorCode.INVALID_ARGUMENTS


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_full_local_policy_rejects_remote_and_missing_drives(
    monkeypatch,
    tmp_path: Path,
):
    application_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    application_root.mkdir()
    user_home.mkdir()
    policy = HostAccessPolicy.full_local(
        application_root=application_root,
        user_home=user_home,
        acknowledged=True,
    )

    monkeypatch.setattr(
        host_access,
        "_windows_drive_type",
        lambda _root: WindowsDriveType.REMOTE,
    )
    with pytest.raises(CapabilityExecutionError) as remote:
        policy.resolve_read(r"Z:\project\file.txt")
    assert remote.value.code == CapabilityErrorCode.PERMISSION_DENIED

    monkeypatch.setattr(
        host_access,
        "_windows_drive_type",
        lambda _root: WindowsDriveType.NO_ROOT_DIRECTORY,
    )
    with pytest.raises(CapabilityExecutionError) as missing:
        policy.resolve_read(r"Z:\project\file.txt")
    assert missing.value.code == CapabilityErrorCode.INACCESSIBLE


def test_phase9_policy_is_connected_without_expanding_the_capability_catalog():
    root = Path(__file__).resolve().parents[1]
    production = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in (
            "app/agent_bootstrap.py",
            "app/agent_config.py",
            "app/main.py",
            "config/agent.json",
        )
    )

    assert "HostAccessPolicy" in production
    assert "full_local_read_enabled" in production
    assert "filesystem.list" not in production
    assert "filesystem.read_text" not in production
    assert "filesystem.search" not in production
