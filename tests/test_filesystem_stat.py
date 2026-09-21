from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityErrorCode,
    PermissionClass,
)
from app.capabilities.filesystem_stat import FilesystemStatCapability
from app.runtime.cancellation import CancellationSource


def context(root: Path, *, allowed: tuple[Path, ...] | None = None) -> CapabilityContext:
    return CapabilityContext(
        call_id="call-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=allowed if allowed is not None else (root,),
        cancellation=CancellationSource().token,
    )


def test_stat_file_returns_normalized_metadata_without_content(tmp_path: Path):
    target = tmp_path / "sample.txt"
    target.write_text("private content", encoding="utf-8")

    result = FilesystemStatCapability().invoke({"path": str(target)}, context(tmp_path))

    assert result.success and result.error is None
    assert result.capability == "filesystem.stat"
    assert result.metadata["permission"] == PermissionClass.READ.value
    assert result.output == {
        "path": str(target.resolve()),
        "type": "file",
        "size_bytes": len("private content"),
        "modified_at": result.output["modified_at"],
        "created_at": result.output["created_at"],
        "is_symlink": False,
        "is_reparse_point": False,
    }
    assert "private content" not in result.model_dump_json()


def test_stat_directory_and_relative_path(tmp_path: Path):
    directory = tmp_path / "folder"
    directory.mkdir()

    result = FilesystemStatCapability().invoke({"path": "folder"}, context(tmp_path))

    assert result.success
    assert result.output["path"] == str(directory.resolve())
    assert result.output["type"] == "directory"
    assert result.output["size_bytes"] is None


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"path": 123},
        {"path": "file.txt", "extra": True},
        {"path": ""},
    ],
)
def test_stat_rejects_invalid_arguments(tmp_path: Path, arguments):
    result = FilesystemStatCapability().invoke(arguments, context(tmp_path))

    assert not result.success
    assert result.output is None
    assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
    assert result.error.details


def test_stat_schema_forbids_unknown_fields():
    schema = FilesystemStatCapability.arguments_model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["required"] == ["path"]
    assert schema["additionalProperties"] is False
    path_description = schema["properties"]["path"]["description"]
    assert "absolute path exactly" in path_description
    assert "never shorten or rewrite" in path_description
    assert "do not prefix the root directory's name" in path_description


def test_stat_returns_stable_not_found_error(tmp_path: Path):
    result = FilesystemStatCapability().invoke(
        {"path": "missing.txt"},
        context(tmp_path),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.NOT_FOUND
    assert "missing.txt" not in result.error.message


def test_stat_denies_traversal_outside_allowed_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    result = FilesystemStatCapability().invoke(
        {"path": "../outside.txt"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED


def test_stat_denies_prefix_sibling_bypass(tmp_path: Path):
    allowed = tmp_path / "work"
    sibling = tmp_path / "work-secret"
    allowed.mkdir()
    sibling.mkdir()
    target = sibling / "secret.txt"
    target.write_text("secret", encoding="utf-8")

    result = FilesystemStatCapability().invoke(
        {"path": str(target)},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED


def test_stat_denies_when_no_read_roots_are_enabled(tmp_path: Path):
    result = FilesystemStatCapability().invoke(
        {"path": str(tmp_path)},
        context(tmp_path, allowed=()),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED


@pytest.mark.skipif(os.name != "nt", reason="UNC paths are Windows-specific.")
def test_stat_denies_unc_paths_without_accessing_the_network(tmp_path: Path):
    result = FilesystemStatCapability().invoke(
        {"path": r"\\server\share\file.txt"},
        context(tmp_path),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED


def test_stat_honors_pre_execution_cancellation(tmp_path: Path):
    source = CancellationSource()
    source.cancel("stop")
    cancelled = CapabilityContext(
        call_id="call-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=tmp_path,
        allowed_read_roots=(tmp_path,),
        cancellation=source.token,
    )

    result = FilesystemStatCapability().invoke({"path": str(tmp_path)}, cancelled)

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


def test_stat_denies_symlink_escape_when_supported(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    link = allowed / "escape.txt"
    try:
        os.symlink(secret, link)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this Windows configuration.")

    result = FilesystemStatCapability().invoke(
        {"path": str(link)},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
