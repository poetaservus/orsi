from copy import deepcopy
import hashlib
import json

import pytest

from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
from app.conversation.recovery import recover_context_request
from tests.test_filesystem_read_text import context
from tests.test_context_recovery import CharacterModel


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_pages_reconstruct_large_unicode_source_exactly(tmp_path, encoding, newline):
    text = ("line π é 😀" + newline) * 1300 + "def final_target(): return 42"
    path = tmp_path / "source.py"
    raw = text.encode(encoding)
    path.write_bytes(raw)
    args, parts, offsets = {"path": str(path), "encoding": encoding, "max_bytes": 127, "max_lines": 3}, [], []
    while args:
        receipt = FilesystemReadTextCapability().invoke(args, context(tmp_path))
        assert receipt.success, receipt.error
        page = receipt.output
        parts.append(page["text"])
        offsets.append(page["offset"])
        assert page["bytes_read"] <= 127
        assert page["bytes_returned"] == page["end_offset"] - page["offset"]
        assert not page["source_complete"]
        assert page["sha256"] is None
        args = page["next_read"]
    assert "".join(parts) == text
    assert offsets == sorted(set(offsets))
    assert page["end_offset"] == len(raw) and not page["has_more"]


def test_projection_continuation_does_not_skip_unseen_source(tmp_path):
    path = tmp_path / "source.py"
    text = "π😀abc\r\n" * 9000 + "last_target"
    path.write_bytes(text.encode())
    output = FilesystemReadTextCapability().invoke({"path": str(path), "max_bytes": 65536, "max_lines": 1000}, context(tmp_path)).output
    original = deepcopy(output)
    projected = recover_context_request(CharacterModel(), [{"role": "user", "content": "Read source"},
        {"role": "capability", "result": {"capability": "filesystem.read_text", "success": True, "output": output}}]).messages[-1]["result"]["output"]
    assert output == original
    assert original["text"].startswith(projected["text"])
    next_page = FilesystemReadTextCapability().invoke(projected["next_read"], context(tmp_path)).output
    assert text.startswith(projected["text"] + next_page["text"])
    assert projected["next_offset"] < original["end_offset"]


def test_changed_revision_requires_restart_and_offsets_require_revision(tmp_path):
    path = tmp_path / "source.py"
    path.write_bytes(b"abcdef")
    tool = FilesystemReadTextCapability()
    first = tool.invoke({"path": str(path), "max_bytes": 3}, context(tmp_path)).output
    assert not tool.invoke({"path": str(path), "offset": 3}, context(tmp_path)).success
    path.write_bytes(b"ABCDEF")
    stale = tool.invoke(first["next_read"], context(tmp_path))
    assert not stale.success and "revision changed" in stale.error.message
    assert tool.invoke({"path": str(path)}, context(tmp_path)).output["sha256"] == hashlib.sha256(b"ABCDEF").hexdigest()


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_tiny_limit_has_a_progressing_continuation(tmp_path, encoding):
    path = tmp_path / "source.py"
    path.write_bytes("😀next".encode(encoding))
    tool = FilesystemReadTextCapability()
    first = tool.invoke({"path": str(path), "encoding": encoding, "max_bytes": 1}, context(tmp_path)).output
    assert first["text"] == ""
    args, parts = first["next_read"], []
    while args:
        page = tool.invoke(args, context(tmp_path)).output
        parts.append(page["text"])
        args = page["next_read"]
    assert "".join(parts) == "😀next"


@pytest.mark.parametrize("encoding,text", [("utf-8", '\\"' * 40000), ("utf-16", "界😀" * 20000)],
    ids=["escaped-utf8", "unicode-utf16"])
def test_large_encoded_pages_fit_the_result_limit_and_keep_continuation(tmp_path, encoding, text):
    path = tmp_path / "huge.py"
    path.write_bytes(text.encode(encoding))
    tool = FilesystemReadTextCapability()
    args, pieces = {"path": str(path), "encoding": encoding, "max_bytes": 65536, "max_lines": 1000}, []
    first = None
    while args:
        result = tool.invoke(args, context(tmp_path))
        assert result.success
        page = result.output
        first = first or page
        assert len(json.dumps(page, ensure_ascii=False).encode()) < 64 * 1024
        pieces.append(page["text"])
        args = page["next_read"]
    assert first["truncated_by_output"] and first["next_read"]
    assert "".join(pieces) == text
