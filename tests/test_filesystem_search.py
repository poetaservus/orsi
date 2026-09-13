from __future__ import annotations

import os
from pathlib import Path

import pytest

import app.capabilities.filesystem_search as search_module
from app.capabilities import (
    CapabilityContext,
    CapabilityErrorCode,
    FilesystemSearchCapability,
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
        call_id="search-call-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=allowed if allowed is not None else (root,),
        cancellation=cancellation or CancellationSource().token,
        host_access_policy=host_access_policy,
    )


def test_search_returns_bounded_literal_matches_without_regex(tmp_path: Path):
    (tmp_path / "b.txt").write_text("alpha NEEDLE beta\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("needle in first file\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"NEEDLE\x00secret")
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "deep.txt").write_text("deep needle\n", encoding="utf-8")

    result = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle", "max_matches": 10},
        context(tmp_path),
    )

    assert result.success and result.error is None
    assert result.capability == "filesystem.search"
    assert result.metadata["permission"] == PermissionClass.READ.value
    assert result.output["path"] == str(tmp_path.resolve())
    assert result.output["query"] == "needle"
    assert result.output["content_is_untrusted"] is True
    assert result.output["returned_matches"] == 3
    assert [match["relative_path"] for match in result.output["matches"]] == [
        "a.txt",
        "b.txt",
        str(Path("folder") / "deep.txt"),
    ]
    serialized = result.model_dump_json()
    assert "secret" not in serialized


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"path": 123, "query": "needle"},
        {"path": ".", "query": ""},
        {"path": ".", "query": "needle", "extra": True},
        {"path": ".", "query": "needle", "case_sensitive": "false"},
        {"path": ".", "query": "needle", "max_depth": 9},
        {"path": ".", "query": "needle", "max_files": 0},
        {"path": ".", "query": "needle", "max_file_bytes": 65_537},
        {"path": ".", "query": "needle", "max_matches": 101},
        {"path": ".", "query": "needle", "snippet_chars": 20},
    ],
)
def test_search_rejects_invalid_arguments(tmp_path: Path, arguments):
    result = FilesystemSearchCapability().invoke(arguments, context(tmp_path))

    assert not result.success
    assert result.output is None
    assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_search_schema_is_strict_and_documents_bounds():
    schema = FilesystemSearchCapability.arguments_model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["required"] == ["path", "query"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["max_depth"]["maximum"] == 8
    assert schema["properties"]["max_files"]["maximum"] == 1_024
    assert schema["properties"]["max_file_bytes"]["maximum"] == 65_536
    assert schema["properties"]["max_matches"]["maximum"] == 100
    assert "Literal text" in schema["properties"]["query"]["description"]


def test_search_applies_depth_match_file_and_entry_bounds(monkeypatch, tmp_path: Path):
    shallow = tmp_path / "shallow.txt"
    shallow.write_text("needle shallow\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "deep.txt").write_text("needle deep\n", encoding="utf-8")

    depth_zero = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle", "max_depth": 0, "max_matches": 10},
        context(tmp_path),
    )
    truncated = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle", "max_matches": 1},
        context(tmp_path),
    )
    too_many_files = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle", "max_files": 1},
        context(tmp_path),
    )
    monkeypatch.setattr(search_module, "MAX_SEARCH_ENTRIES", 1)
    too_many_entries = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle"},
        context(tmp_path),
    )

    assert depth_zero.success
    assert [match["relative_path"] for match in depth_zero.output["matches"]] == [
        "shallow.txt"
    ]
    assert truncated.success
    assert truncated.output["returned_matches"] == 1
    assert truncated.output["truncated_by_matches"] is True
    assert not too_many_files.success
    assert too_many_files.error.code == CapabilityErrorCode.OUTPUT_LIMITED
    assert not too_many_entries.success
    assert too_many_entries.error.code == CapabilityErrorCode.OUTPUT_LIMITED


def test_search_returns_stable_missing_and_not_directory_failures(tmp_path: Path):
    missing = FilesystemSearchCapability().invoke(
        {"path": "missing", "query": "needle"},
        context(tmp_path),
    )
    file_path = tmp_path / "file.txt"
    file_path.write_text("needle", encoding="utf-8")
    not_directory = FilesystemSearchCapability().invoke(
        {"path": "file.txt", "query": "needle"},
        context(tmp_path),
    )

    assert not missing.success
    assert missing.error.code == CapabilityErrorCode.NOT_FOUND
    assert not not_directory.success
    assert not_directory.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_search_denies_paths_outside_allowed_roots_without_reading(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = "OUTSIDE-NEEDLE-MUST-NOT-LEAK"
    (outside / "secret.txt").write_text(secret, encoding="utf-8")

    result = FilesystemSearchCapability().invoke(
        {"path": "../outside", "query": "NEEDLE"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
    assert secret not in result.model_dump_json()


def test_search_honors_pre_execution_cancellation(tmp_path: Path):
    source = CancellationSource()
    source.cancel("stop")

    result = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle"},
        context(tmp_path, cancellation=source.token),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


def test_search_denies_symlink_escape_when_supported(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("needle secret", encoding="utf-8")
    link = allowed / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks is unavailable on this configuration.")

    result = FilesystemSearchCapability().invoke(
        {"path": ".", "query": "needle"},
        context(allowed),
    )

    assert result.success
    assert result.output["matches"] == []
    assert "secret" not in result.model_dump_json()


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_search_full_local_policy_reads_outside_portable_root(tmp_path: Path):
    portable_root = tmp_path / "portable"
    user_home = tmp_path / "home"
    host_directory = tmp_path / "host-directory"
    portable_root.mkdir()
    user_home.mkdir()
    host_directory.mkdir()
    target = host_directory / "host-note.txt"
    target.write_text("needle host text", encoding="utf-8")
    policy = HostAccessPolicy.full_local(
        application_root=portable_root,
        user_home=user_home,
        acknowledged=True,
    )

    result = FilesystemSearchCapability().invoke(
        {"path": str(host_directory), "query": "needle"},
        context(
            portable_root,
            allowed=policy.permission_roots(),
            host_access_policy=policy,
        ),
    )

    assert result.success
    assert result.output["matches"][0]["relative_path"] == "host-note.txt"
    assert not str(host_directory.resolve()).startswith(str(portable_root.resolve()))
