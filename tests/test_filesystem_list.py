from __future__ import annotations

import os
from pathlib import Path

import pytest

import app.capabilities.filesystem_list as filesystem_list_module
from app.capabilities.contracts import (
    CapabilityContext,
    CapabilityErrorCode,
    PermissionClass,
)
from app.capabilities.filesystem_list import FilesystemListCapability
from app.security.host_access import HostAccessPolicy
from app.runtime.cancellation import CancellationSource


def context(
    root: Path,
    *,
    allowed: tuple[Path, ...] | None = None,
    host_access_policy: HostAccessPolicy | None = None,
    cancellation=None,
) -> CapabilityContext:
    return CapabilityContext(
        call_id="list-call-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=allowed if allowed is not None else (root,),
        cancellation=cancellation or CancellationSource().token,
        host_access_policy=host_access_policy,
    )


def test_list_returns_sorted_bounded_names_and_types_without_content(tmp_path: Path):
    (tmp_path / "B.txt").write_text("PRIVATE-B-CONTENT", encoding="utf-8")
    (tmp_path / "a.txt").write_text("PRIVATE-A-CONTENT", encoding="utf-8")
    (tmp_path / "Folder").mkdir()

    result = FilesystemListCapability().invoke({"path": "."}, context(tmp_path))

    assert result.success and result.error is None
    assert result.capability == "filesystem.list"
    assert result.metadata["permission"] == PermissionClass.READ.value
    assert result.output["path"] == str(tmp_path.resolve())
    assert [entry["name"] for entry in result.output["entries"]] == [
        "a.txt",
        "B.txt",
        "Folder",
    ]
    assert [entry["type"] for entry in result.output["entries"]] == [
        "file",
        "file",
        "directory",
    ]
    assert result.output["returned_entries"] == 3
    assert result.output["total_entries"] == 3
    assert result.output["next_cursor"] is None
    assert result.output["has_more"] is False
    serialized = result.model_dump_json()
    assert "PRIVATE-A-CONTENT" not in serialized
    assert "PRIVATE-B-CONTENT" not in serialized


def test_list_paginates_without_duplicates_and_finishes(tmp_path: Path):
    for name in ("echo.txt", "alpha.txt", "delta.txt", "bravo.txt", "charlie.txt"):
        (tmp_path / name).touch()
    capability = FilesystemListCapability()
    first = capability.invoke(
        {"path": ".", "max_entries": 2},
        context(tmp_path),
    )
    second = capability.invoke(
        {
            "path": ".",
            "max_entries": 2,
            "cursor": first.output["next_cursor"],
        },
        context(tmp_path),
    )
    third = capability.invoke(
        {
            "path": ".",
            "max_entries": 2,
            "cursor": second.output["next_cursor"],
        },
        context(tmp_path),
    )

    assert first.success and second.success and third.success
    names = [
        entry["name"]
        for result in (first, second, third)
        for entry in result.output["entries"]
    ]
    assert names == [
        "alpha.txt",
        "bravo.txt",
        "charlie.txt",
        "delta.txt",
        "echo.txt",
    ]
    assert len(names) == len(set(names))
    assert first.output["has_more"] is True
    assert second.output["has_more"] is True
    assert third.output["has_more"] is False
    assert third.output["next_cursor"] is None


def test_list_rejects_cursor_after_directory_changes(tmp_path: Path):
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.txt").touch()
    first = FilesystemListCapability().invoke(
        {"path": ".", "max_entries": 1},
        context(tmp_path),
    )
    (tmp_path / "c.txt").touch()

    changed = FilesystemListCapability().invoke(
        {
            "path": ".",
            "max_entries": 1,
            "cursor": first.output["next_cursor"],
        },
        context(tmp_path),
    )

    assert not changed.success
    assert changed.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
    assert "changed" in changed.error.message


def test_list_cursor_is_bound_to_the_exact_directory(tmp_path: Path):
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    (first_directory / "a.txt").touch()
    (first_directory / "b.txt").touch()
    (second_directory / "a.txt").touch()
    (second_directory / "b.txt").touch()
    first = FilesystemListCapability().invoke(
        {"path": "first", "max_entries": 1},
        context(tmp_path),
    )

    wrong_directory = FilesystemListCapability().invoke(
        {
            "path": "second",
            "max_entries": 1,
            "cursor": first.output["next_cursor"],
        },
        context(tmp_path),
    )

    assert not wrong_directory.success
    assert wrong_directory.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
    assert "different path" in wrong_directory.error.message


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"path": 123},
        {"path": ".", "extra": True},
        {"path": ""},
        {"path": ".", "max_entries": 0},
        {"path": ".", "max_entries": 51},
        {"path": ".", "max_entries": "10"},
        {"path": ".", "cursor": "not_a_real_cursor"},
    ],
)
def test_list_rejects_invalid_arguments_or_cursors(tmp_path: Path, arguments):
    result = FilesystemListCapability().invoke(arguments, context(tmp_path))

    assert not result.success
    assert result.output is None
    assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_list_schema_is_strict_and_documents_pagination():
    schema = FilesystemListCapability.arguments_model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["required"] == ["path"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["max_entries"]["maximum"] == 50
    assert "next_cursor exactly" in schema["properties"]["cursor"]["description"]
    assert "requested directory path exactly" in schema["properties"]["path"][
        "description"
    ]


def test_list_returns_stable_missing_and_not_directory_failures(tmp_path: Path):
    missing = FilesystemListCapability().invoke(
        {"path": "missing"},
        context(tmp_path),
    )
    file_path = tmp_path / "file.txt"
    file_path.touch()
    not_directory = FilesystemListCapability().invoke(
        {"path": "file.txt"},
        context(tmp_path),
    )

    assert not missing.success
    assert missing.error.code == CapabilityErrorCode.NOT_FOUND
    assert not not_directory.success
    assert not_directory.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_list_denies_traversal_outside_portable_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret-name.txt").touch()

    result = FilesystemListCapability().invoke(
        {"path": "../outside"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_list_full_local_policy_reads_outside_portable_root(tmp_path: Path):
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    host_directory = tmp_path / "host-directory"
    portable_root.mkdir()
    user_home.mkdir()
    host_directory.mkdir()
    (host_directory / "host-file.txt").touch()
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )

    result = FilesystemListCapability().invoke(
        {"path": str(host_directory)},
        context(
            portable_root,
            allowed=policy.permission_roots(),
            host_access_policy=policy,
        ),
    )

    assert result.success
    assert result.output["entries"][0]["name"] == "host-file.txt"
    assert not str(host_directory.resolve()).startswith(str(portable_root.resolve()))


def test_list_enforces_total_directory_entry_bound(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(filesystem_list_module, "MAX_DIRECTORY_ENTRIES", 2)
    for index in range(3):
        (tmp_path / f"entry-{index}.txt").touch()

    result = FilesystemListCapability().invoke({"path": "."}, context(tmp_path))

    assert not result.success
    assert result.error.code == CapabilityErrorCode.OUTPUT_LIMITED


def test_list_honors_pre_execution_cancellation(tmp_path: Path):
    source = CancellationSource()
    source.cancel("stop")

    result = FilesystemListCapability().invoke(
        {"path": "."},
        context(tmp_path, cancellation=source.token),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


def test_list_honors_cancellation_while_scanning(monkeypatch, tmp_path: Path):
    source = CancellationSource()
    for index in range(2):
        (tmp_path / f"entry-{index}.txt").touch()
    original_summary = filesystem_list_module._entry_summary

    def cancel_after_first_entry(item):
        summary = original_summary(item)
        source.cancel("stop during scan")
        return summary

    monkeypatch.setattr(filesystem_list_module, "_entry_summary", cancel_after_first_entry)

    result = FilesystemListCapability().invoke(
        {"path": "."},
        context(tmp_path, cancellation=source.token),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


def test_list_denies_symlink_escape_when_supported(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret-name.txt").touch()
    link = allowed / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks is unavailable on this configuration.")

    result = FilesystemListCapability().invoke(
        {"path": "escape"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
