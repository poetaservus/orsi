"""Portable installations cannot reproduce; node identities survive relocation."""
import json

import pytest

import app.portable.deployment as deployment
from app.portable.deployment import DeploymentError, MANIFEST, deploy_node, verify_node
from app.portable.identity import is_deployed_node
from app.runtime.cancellation import CancellationSource, TaskCancelled
from app.state.storage import JsonStore
from app.vault.profiles import ProfileManager
from tests.test_portable_deployment import manager, source


@pytest.mark.parametrize("marker", [MANIFEST, "PACKAGE_MANIFEST.json"])
@pytest.mark.parametrize("include_profile", [False, True])
def test_existing_portable_and_pilot_markers_block_all_deployment(manager, marker, include_profile):
    (manager.application_root / marker).write_text("damaged manifest")
    target = manager.application_root.parent / "forbidden node"
    with pytest.raises(DeploymentError, match="Portable nodes cannot deploy"):
        deploy_node(manager, target, include_profile=include_profile)
    assert not target.exists() and manager.active
    assert not (manager.application_root / "state/portable_deployment_v1.json").exists()


def test_numbering_and_relocated_fresh_node_restriction(manager):
    root = manager.application_root
    first = deploy_node(manager, root.parent / "first node", include_profile=False)
    second = deploy_node(manager, root.parent / "second node")
    assert (first.node_number, second.node_number) == (1, 2)
    for result in (first, second):
        manifest = json.loads((result.destination / MANIFEST).read_text())
        assert manifest["node_number"] == result.node_number and manifest["can_deploy_nodes"] is False
        assert manifest["node_name"] == f"O.R.S.I Portable Node Nr. {result.node_number:03d}"
        assert (result.destination / "START_HERE.txt").read_text().startswith(manifest["node_name"])
        assert not (result.destination / "state/portable_deployment_v1.json").exists()
        assert verify_node(result.destination) == result.files_verified
    moved = root.parent / "relocated fresh node"
    first.destination.rename(moved)
    assert is_deployed_node(moved)
    copied = ProfileManager(moved)
    with pytest.raises(DeploymentError, match="Portable nodes cannot deploy"):
        deploy_node(copied, root.parent / "offspring", include_profile=False)
    assert JsonStore(root / "state/portable_deployment_v1.json").load()["next_number"] == 3
    assert manager.active


def test_invalid_counter_is_preserved_and_no_node_is_published(manager):
    counter = manager.application_root / "state/portable_deployment_v1.json"
    counter.write_bytes(b"unrecognized existing instance state")
    target = manager.application_root.parent / "bad counter node"
    with pytest.raises(DeploymentError, match="node number could not be saved"):
        deploy_node(manager, target)
    assert counter.read_bytes() == b"unrecognized existing instance state"
    assert not target.exists() and manager.active


def test_cancelled_export_does_not_rename_drive_or_reuse_reserved_number(manager, monkeypatch):
    renamed = []
    monkeypatch.setattr(deployment, "finish_drive_label", lambda *args: renamed.append(args))
    cancellation = CancellationSource()
    def cancel(value, phase):
        if phase == "Copying node…":
            cancellation.cancel()
    with pytest.raises(TaskCancelled):
        deploy_node(manager, manager.application_root.parent / "cancelled node",
                    token=cancellation.token, progress=cancel)
    assert not renamed and manager.active
    assert JsonStore(manager.application_root / "state/portable_deployment_v1.json").load()["next_number"] == 2
