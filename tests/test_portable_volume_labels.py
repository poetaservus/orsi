"""Volume naming uses captured identities and never targets internal/system disks."""
import os

import pytest

import app.portable.volumes as volumes
from app.portable.deployment import deploy_node
from app.portable.volumes import Volume, prepare_drive_label, finish_drive_label
from tests.test_portable_deployment import manager, source


class FakeVolumes:
    def __init__(self, root, *, filesystem="NTFS", drive_type=3, bus_type=7):
        self.root = root
        self.source = Volume("C:\\", "source-volume", "NTFS", 3, 17)
        self.system = Volume("C:\\", "system-volume", "NTFS", 3, 17)
        self.target = Volume("E:\\", "external-volume", filesystem, drive_type, bus_type)
        self.renamed = []
        self.fail_rename = False

    def system_directory(self):
        return "Windows-system-directory"

    def inspect(self, path):
        if str(path) == "Windows-system-directory":
            return self.system
        return self.source if path == self.root else self.target

    def set_label(self, identity, label):
        if self.fail_rename:
            raise PermissionError("synthetic private error detail")
        self.renamed.append((identity, label))


@pytest.mark.parametrize("filesystem,drive_type,bus_type,label", [
    ("NTFS", 3, 7, "O.R.S.I Portable Node Nr. 001"),
    ("exFAT", 3, 7, "ORSI 001"),
    ("FAT32", 2, 0, "ORSI 001"),
])
def test_external_volume_named_only_after_verified_publication(manager, monkeypatch, filesystem, drive_type, bus_type, label):
    root = manager.application_root
    api = FakeVolumes(root, filesystem=filesystem, drive_type=drive_type, bus_type=bus_type)
    monkeypatch.setattr(volumes, "_windows_api", lambda: api)
    target = root.parent / "named node"
    original_set = api.set_label
    def observe(identity, name):
        assert target.is_dir() and (target / "NODE_MANIFEST.json").is_file()
        original_set(identity, name)
    api.set_label = observe
    result = deploy_node(manager, target)
    assert result.drive_label == label and api.renamed == [("external-volume", label)]
    assert label in result.drive_message and manager.active


@pytest.mark.parametrize("reason", ["source", "system", "internal", "network", "unsupported"])
def test_protected_or_unsupported_destinations_keep_original_label(tmp_path, monkeypatch, reason):
    api = FakeVolumes(tmp_path)
    if reason == "source":
        api.target = api.source
    elif reason == "system":
        api.target = api.system
    elif reason == "internal":
        api.target = Volume("D:\\", "internal-volume", "NTFS", 3, 17)
    elif reason == "network":
        api.target = Volume("Z:\\", "network-volume", "NTFS", 4)
    else:
        api.target = Volume("E:\\", "external-volume", "unknown", 2)
    monkeypatch.setattr(volumes, "_windows_api", lambda: api)
    plan = prepare_drive_label(tmp_path.parent, tmp_path, 1)
    result = finish_drive_label(plan, tmp_path.parent)
    assert result.label is None and result.message and not api.renamed


def test_replacement_drive_is_not_renamed(tmp_path, monkeypatch):
    api = FakeVolumes(tmp_path)
    monkeypatch.setattr(volumes, "_windows_api", lambda: api)
    plan = prepare_drive_label(tmp_path.parent, tmp_path, 1)
    api.target = Volume("E:\\", "different-volume", "NTFS", 3, 7)
    result = finish_drive_label(plan, tmp_path.parent)
    assert result.label is None and "drive changed" in result.message and not api.renamed


def test_rename_denied_reports_ready_node_without_exposing_error(manager, monkeypatch):
    api = FakeVolumes(manager.application_root)
    api.fail_rename = True
    monkeypatch.setattr(volumes, "_windows_api", lambda: api)
    result = deploy_node(manager, manager.application_root.parent / "rename denied")
    assert result.destination.is_dir() and result.drive_label is None and result.copy_registered
    assert "Windows could not rename" in result.drive_message and "private" not in result.drive_message
    assert manager.active


def test_unreadable_volume_metadata_leaves_label_unchanged(tmp_path, monkeypatch):
    def denied():
        raise PermissionError("synthetic private error detail")
    monkeypatch.setattr(volumes, "_windows_api", denied)
    result = prepare_drive_label(tmp_path.parent, tmp_path, 1)
    assert isinstance(result, volumes.DriveLabelResult) and result.label is None
    assert "private" not in result.message


@pytest.mark.skipif(os.name != "nt", reason="Windows volume metadata API")
def test_real_windows_metadata_and_same_volume_guard(tmp_path):
    api = volumes.WindowsVolumes()
    actual = api.inspect(tmp_path)
    assert actual.identity.startswith("\\\\?\\Volume{") and actual.filesystem and actual.root.endswith("\\")
    assert api.inspect(api.system_directory()).identity
    plan = prepare_drive_label(tmp_path, tmp_path, 1)
    assert isinstance(plan, volumes.DriveLabelResult) and plan.label is None
