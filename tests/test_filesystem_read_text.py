from __future__ import annotations

import os
from pathlib import Path

import pytest

import app.capabilities.filesystem_read_text as read_text_module
from app.capabilities import (
    CapabilityContext,
    CapabilityErrorCode,
    FilesystemReadTextCapability,
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
        call_id="read-text-call-1",
        session_id="session-1",
        turn_id="turn-1",
        portable_root=root,
        allowed_read_roots=allowed if allowed is not None else (root,),
        cancellation=cancellation or CancellationSource().token,
        host_access_policy=host_access_policy,
    )


def test_read_text_returns_bounded_untrusted_text(tmp_path: Path):
    target = tmp_path / "note.txt"
    target.write_bytes("first line\nsecond line\n".encode("utf-8"))

    result = FilesystemReadTextCapability().invoke(
        {"path": "note.txt", "max_bytes": 100, "max_lines": 10},
        context(tmp_path),
    )

    assert result.success and result.error is None
    assert result.capability == "filesystem.read_text"
    assert result.metadata["permission"] == PermissionClass.READ.value
    assert result.output == {
        "path": str(target.resolve()),
        "encoding": "utf-8",
        "text": "first line\nsecond line\n",
        "bytes_read": len("first line\nsecond line\n".encode("utf-8")),
        "total_size_bytes": target.stat().st_size,
        "lines_returned": 2,
        "truncated_by_bytes": False,
        "truncated_by_lines": False,
        "content_is_untrusted": True,
    }


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"path": 123},
        {"path": "note.txt", "extra": True},
        {"path": ""},
        {"path": "note.txt", "encoding": "latin-1"},
        {"path": "note.txt", "max_bytes": 0},
        {"path": "note.txt", "max_bytes": 65_537},
        {"path": "note.txt", "max_lines": 0},
        {"path": "note.txt", "max_lines": 1_001},
    ],
)
def test_read_text_rejects_invalid_arguments(tmp_path: Path, arguments):
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")

    result = FilesystemReadTextCapability().invoke(arguments, context(tmp_path))

    assert not result.success
    assert result.output is None
    assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_read_text_schema_is_strict_and_documents_limits():
    schema = FilesystemReadTextCapability.arguments_model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["required"] == ["path"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["max_bytes"]["maximum"] == 65_536
    assert schema["properties"]["max_lines"]["maximum"] == 1_000
    assert "requested text-file path exactly" in schema["properties"]["path"]["description"]
    assert set(schema["properties"]["encoding"]["enum"]) == {
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
    }


def test_read_text_applies_byte_and_line_limits(tmp_path: Path):
    byte_target = tmp_path / "bytes.txt"
    byte_target.write_bytes(b"abcdef")
    line_target = tmp_path / "lines.txt"
    line_target.write_bytes(b"one\ntwo\nthree\n")

    by_bytes = FilesystemReadTextCapability().invoke(
        {"path": "bytes.txt", "max_bytes": 3},
        context(tmp_path),
    )
    by_lines = FilesystemReadTextCapability().invoke(
        {"path": "lines.txt", "max_lines": 2},
        context(tmp_path),
    )

    assert by_bytes.success
    assert by_bytes.output["text"] == "abc"
    assert by_bytes.output["bytes_read"] == 3
    assert by_bytes.output["truncated_by_bytes"] is True
    assert by_lines.success
    assert by_lines.output["text"] == "one\ntwo\n"
    assert by_lines.output["lines_returned"] == 2
    assert by_lines.output["truncated_by_lines"] is True


def test_read_text_supports_declared_utf_encodings(tmp_path: Path):
    target = tmp_path / "utf16.txt"
    target.write_bytes("hello\n".encode("utf-16"))

    result = FilesystemReadTextCapability().invoke(
        {"path": "utf16.txt", "encoding": "utf-16"},
        context(tmp_path),
    )

    assert result.success
    assert result.output["text"] == "hello\n"
    assert result.output["encoding"] == "utf-16"


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\xfe\x00\x00",
        b"hello\x01there",
    ],
)
def test_read_text_rejects_binary_or_non_text_payloads(tmp_path: Path, payload: bytes):
    target = tmp_path / "binary.dat"
    target.write_bytes(payload)

    result = FilesystemReadTextCapability().invoke(
        {"path": "binary.dat"},
        context(tmp_path),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS
    assert result.output is None


def test_read_text_returns_stable_missing_and_directory_failures(tmp_path: Path):
    directory = tmp_path / "folder"
    directory.mkdir()

    missing = FilesystemReadTextCapability().invoke(
        {"path": "missing.txt"},
        context(tmp_path),
    )
    directory_result = FilesystemReadTextCapability().invoke(
        {"path": "folder"},
        context(tmp_path),
    )

    assert not missing.success
    assert missing.error.code == CapabilityErrorCode.NOT_FOUND
    assert not directory_result.success
    assert directory_result.error.code == CapabilityErrorCode.INVALID_ARGUMENTS


def test_read_text_denies_paths_outside_allowed_roots_without_reading(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = "OUTSIDE-CONTENT-MUST-NOT-LEAK"
    (outside / "secret.txt").write_text(secret, encoding="utf-8")

    result = FilesystemReadTextCapability().invoke(
        {"path": "../outside/secret.txt"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
    assert secret not in result.model_dump_json()


def test_read_text_denies_when_no_read_roots_are_enabled(tmp_path: Path):
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")

    result = FilesystemReadTextCapability().invoke(
        {"path": str(target)},
        context(tmp_path, allowed=()),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED


def test_read_text_honors_pre_execution_cancellation(tmp_path: Path):
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    source = CancellationSource()
    source.cancel("stop")

    result = FilesystemReadTextCapability().invoke(
        {"path": "note.txt"},
        context(tmp_path, cancellation=source.token),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


def test_read_text_honors_cancellation_after_file_read(monkeypatch, tmp_path: Path):
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    source = CancellationSource()
    original = read_text_module._read_bounded_bytes

    def cancel_after_read(path, max_bytes, call_context):
        value = original(path, max_bytes, call_context)
        source.cancel("stop after read")
        return value

    monkeypatch.setattr(read_text_module, "_read_bounded_bytes", cancel_after_read)

    result = FilesystemReadTextCapability().invoke(
        {"path": "note.txt"},
        context(tmp_path, cancellation=source.token),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.CANCELLED


@pytest.mark.skipif(os.name != "nt", reason="Full local reads are Windows-specific.")
def test_read_text_full_local_policy_reads_outside_portable_root(tmp_path: Path):
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

    result = FilesystemReadTextCapability().invoke(
        {"path": str(target)},
        context(
            portable_root,
            allowed=policy.permission_roots(),
            host_access_policy=policy,
        ),
    )

    assert result.success
    assert result.output["text"] == "host text"
    assert not str(target.resolve()).startswith(str(portable_root.resolve()))


def test_read_text_denies_symlink_escape_when_supported(tmp_path: Path):
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
        pytest.skip("Creating symlinks is unavailable on this configuration.")

    result = FilesystemReadTextCapability().invoke(
        {"path": "escape.txt"},
        context(allowed),
    )

    assert not result.success
    assert result.error.code == CapabilityErrorCode.PERMISSION_DENIED
