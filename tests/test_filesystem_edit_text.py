from __future__ import annotations

import codecs
import hashlib
import json

import pytest
from pydantic import ValidationError

from app.capabilities.contracts import CapabilityExecutionError
from app.capabilities.filesystem_edit_text import (
    FilesystemEditTextArguments as Args, MAX_FILE_BYTES, plan_edit,
)
from app.conversation.capability_routing import select_turn_capabilities
from app.conversation.prompt import agent_system_prompt, compact_agent_system_prompt
from app.security.host_access import HostReadScope
from app.settings.agent import AgentFeatureConfig
from tests.fixtures.context_reliability import large_css_fixture


def args(**values):
    return Args(path=r"C:\fixture\note.txt", old_text="old", new_text="new", **values)


@pytest.mark.parametrize("values", [
    {"old_text": ""}, {"replace_all": "true"}, {"expected_sha256": "wrong"},
    {"extra": 1}, {"new_text": 3}, {"old_text": "x" * 16385}, {"new_text": "\ud800"},
], ids=["empty", "bool", "digest", "extra", "type", "fragment-limit", "surrogate"])
def test_strict_schema(values):
    with pytest.raises(ValidationError):
        Args.model_validate({"path": r"C:\fixture\note.txt", "old_text": "old",
                             "new_text": "new", **values})


@pytest.mark.parametrize("raw, expected", [
    (b"old\nkeep\n", b"new\nkeep\n"),
    (codecs.BOM_UTF8 + b"old\r\nkeep\r\n", codecs.BOM_UTF8 + b"new\r\nkeep\r\n"),
    (b"old\rkeep\nlast", b"new\rkeep\nlast"),
])
def test_preserves_bom_line_endings_and_missing_final_newline(raw, expected):
    plan = plan_edit(raw, args(expected_sha256=hashlib.sha256(raw).hexdigest()))
    assert plan.data == expected
    assert plan.replacements == 1
    assert plan.additions == plan.deletions == 1
    assert '"-old' in plan.preview and '"+new' in plan.preview


@pytest.mark.parametrize("raw, values, reason", [
    (b"other", {}, "not found"),
    (b"old old", {}, "multiple"),
    (b"aaa", {"old_text": "aa", "new_text": "z", "replace_all": True}, "overlapping"),
    (b"old", {"old_text": "old", "new_text": "old"}, "no change"),
    (b"old\x00", {}, "Binary"),
    (b"old\xff", {}, "UTF-8"),
    (b"old", {"expected_sha256": "0" * 64}, "digest"),
    (b"old" + b"x" * MAX_FILE_BYTES, {}, "1 MiB"),
    (b"old\n" + b"x\n" * 10000, {}, "10,000"),
], ids=["missing", "ambiguous", "overlap", "noop", "binary", "encoding", "digest", "size", "lines"])
def test_invalid_edits_fail_closed(raw, values, reason):
    model = Args(path=r"C:\fixture\note.txt", **{"old_text": "old", "new_text": "new", **values})
    with pytest.raises(CapabilityExecutionError, match=reason):
        plan_edit(raw, model)


def test_replace_all_is_explicit_and_deletion_is_supported():
    plan = plan_edit(b"old\nold\n", Args(path="unused", old_text="old\n", new_text="", replace_all=True))
    assert plan.data == b""
    assert (plan.replacements, plan.additions, plan.deletions) == (2, 0, 2)


def test_large_css_edit_has_small_complete_diff_and_compact_arguments():
    raw = large_css_fixture().encode()
    old = ".phase0-component-001 { color: #123456;"
    model = Args(path="unused", old_text=old, new_text=old.replace("#123456", "#ffffff"))
    plan = plan_edit(raw, model)
    assert plan.data == raw.replace(b"#123456", b"#ffffff", 1)
    assert len(plan.preview) < 2500
    assert len(model.model_dump_json()) < 350


def test_preview_limit_rejects_instead_of_truncating():
    raw = ("old " + "x" * 16000 + "\n").encode()
    with pytest.raises(CapabilityExecutionError, match="approval limit"):
        plan_edit(raw, Args(path="unused", old_text="old", new_text="z" * 16000))


def test_expansion_limit_checked_before_replacement():
    with pytest.raises(CapabilityExecutionError, match="exceed 1 MiB"):
        plan_edit(b"a" * 1000, Args(path="unused", old_text="a", new_text="b" * 16000, replace_all=True))


def test_preview_escapes_invisible_characters_and_counts_header_like_content():
    plan = plan_edit("++old\u202e\r\n".encode(), Args(path="unused", old_text="++old", new_text="--new"))
    assert "\u202e" not in plan.preview
    assert r"\u202e\r\n" in plan.preview
    assert plan.additions == plan.deletions == 1
    assert all(isinstance(json.loads(line), str) for line in plan.preview.splitlines()[1:])


def test_default_off_and_separate_metadata_dependency():
    assert not AgentFeatureConfig().filesystem_edit_text_enabled
    with pytest.raises(ValueError, match="metadata"):
        AgentFeatureConfig(filesystem_edit_text_enabled=True)


def test_edit_routing_and_both_prompt_variants():
    catalog = ("filesystem.stat", "filesystem.list", "filesystem.read_text", "filesystem.edit_text", "filesystem.write_text")
    assert "filesystem.edit_text" in select_turn_capabilities("Change the CSS color", catalog)
    assert "filesystem.read_text" in select_turn_capabilities("Change the CSS color", catalog)
    assert "filesystem.edit_text" not in select_turn_capabilities("Read the file", catalog)
    for prompt in (agent_system_prompt, compact_agent_system_prompt):
        text = prompt(HostReadScope.PORTABLE_ROOT, catalog)
        assert "Prefer filesystem.edit_text" in text
        assert "replace_all" in text and "expected_sha256" in text
