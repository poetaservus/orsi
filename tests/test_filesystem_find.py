from __future__ import annotations

import os
from pathlib import Path

import pytest

import app.capabilities.filesystem_find as find_module
from app.capabilities import (
    CapabilityContext,
    CapabilityErrorCode,
    FilesystemFindCapability,
    PermissionClass,
)
from app.capabilities.host_access import HostAccessPolicy
from app.runtime.cancellation import CancellationSource


def context(
    root: Path,
    *,
    allowed: tuple[Path, ...] | None = None,
    host_access_policy: HostAccessPolicy | None = None,
    cancellation=None,
) -> CapabilityContext:
    return CapabilityContext(
        call_id="find-call-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=allowed if allowed is not None else (root,),
        cancellation=cancellation or CancellationSource().token,
        host_access_policy=host_access_policy,
    )


def test_find_returns_exact_name_matches_without_content(tmp_path: Path):
    target = tmp_path / "Report.txt"
    target.write_text("PRIVATE-REPORT-CONTENT", encoding="utf-8")
    (tmp_path / "Report").mkdir()
    (tmp_path / "report.txt.bak").write_text("backup", encoding="utf-8")

    result = FilesystemFindCapability().invoke(
        {"path": ".", "name": "report.txt", "kind": "file"},
        context(tmp_path),
    )

    assert result.success and result.error is None
    assert result.capability == "filesystem.find"
    assert result.metadata["permission"] == PermissionClass.READ.value
    assert result.output["path"] == str(tmp_path.resolve())
    assert result.output["returned_matches"] == 1
    assert result.output["matches"][0]["name"] == "Report.txt"
    assert result.output["matches"][0]["type"] == "file"
    assert result.output["matches"][0]["path"] == str(target.resolve())
    assert "PRIVATE-REPORT-CONTENT" not in result.model_dump_json()


def test_find_filters_requested_kind(tmp_path: Path):
    (tmp_path / "lab").mkdir()

    missing_file = FilesystemFindCapability().invoke(
        {"path": ".", "name": "lab", "kind": "file"},
        context(tmp_path),
    )
    directory = FilesystemFindCapability().invoke(
        {"path": ".", "name": "lab", "kind": "directory"},
        context(tmp_path),
    )

    assert missing_file.success
    assert missing_file.output["matches"] == []
    assert directory.success
    assert directory.output["matches"][0]["type"] == "directory"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"path": 123, "name": "target"},
        {"path": ".", "name": ""},
        {"path": ".", "name": "target", "extra": True},
        {"path": ".", "name": "folder/name"},
        {"path": ".", "name": r"folder\name"},
        {"path": ".", "name": " target"},
        {"path": ".", "name": "."},
        {"path": ".", "name": "target", "kind": "recursive"},
    ],
)
def test_find_rejects_invalid_arguments(tmp_path: Path, arguments):
    result = FilesystemFindCapability().invoke(arguments, context(tmp_path))

    assert not result.success
    assert result.output is None
    assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_find_schema_is_strict_and_documents_exact_name():
    schema = FilesystemFindCapability.arguments_model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["required"] == ["path", "name"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["name"]["maxLength"] == 255
    assert set(schema["properties"]["kind"]["enum"]) == {"any", "file", "directory"}
    assert "Exact file or folder name" in schema["properties"]["name"]["description"]


def test_find_applies_entry_bound(monkeypatch, tmp_path: Path):
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.txt").touch()
    monkeypatch.setattr(find_module, "MAX_FIND_DIRECTORY_ENTRIES", 1)

    result = FilesystemFindCapability().invoke(
        {"path": ".", "name": "missing.txt"},
        context(tmp_path),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.OUTPUT_LIMITED


def test_find_returns_stable_missing_and_not_directory_failures(tmp_path: Path):
    missing = FilesystemFindCapability().invoke(
        {"path": "missing", "name": "target"},
        context(tmp_path),
    )
    file_path = tmp_path / "file.txt"
    file_path.write_text("target", encoding="utf-8")
    not_directory = FilesystemFindCapability().invoke(
        {"path": "file.txt", "name": "target"},
        context(tmp_path),
    )

    assert not missing.success
    assert missing.error.code == CapabilityErrorCode.NOT_FOUND
    assert not not_directory.success
    assert not_directory.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_find_denies_paths_outside_allowed_roots_without_reading(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = "OUTSIDE-CONTENT-MUST-NOT-LEAK"
    (outside / "secret.txt").write_text(secret, encoding="utf-8")

    result = FilesystemFindCapability().invoke(
        {"path": "../outside", "name": "secret.txt"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
    assert secret not in result.model_dump_json()


def test_find_honors_pre_execution_cancellation(tmp_path: Path):
    source = CancellationSource()
    source.cancel("stop")

    result = FilesystemFindCapability().invoke(
        {"path": ".", "name": "target"},
        context(tmp_path, cancellation=source.token),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_find_full_local_policy_reads_outside_portable_root(tmp_path: Path):
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    host_directory = tmp_path / "host-directory"
    portable_root.mkdir()
    user_home.mkdir()
    host_directory.mkdir()
    target = host_directory / "host-note.txt"
    target.write_text("host text", encoding="utf-8")
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )

    result = FilesystemFindCapability().invoke(
        {"path": str(host_directory), "name": "host-note.txt", "kind": "file"},
        context(
            portable_root,
            allowed=policy.permission_roots(),
            host_access_policy=policy,
        ),
    )

    assert result.success
    assert result.output["matches"][0]["path"] == str(target.resolve())
    assert not str(host_directory.resolve()).startswith(str(portable_root.resolve()))
