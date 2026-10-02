from __future__ import annotations

import pytest

from app.conversation.capability_routing import select_turn_capabilities


CATALOG = (
    "application.launch", "filesystem.copy", "filesystem.find", "filesystem.list",
    "filesystem.mkdir", "filesystem.move", "filesystem.read_text", "filesystem.search",
    "filesystem.stat", "filesystem.trash", "filesystem.write_text",
)


@pytest.mark.parametrize("user_text", (
    "edit style.css and give it a sleek charcoal and violet design",
    "what's in my Documents website folder?", "read the contents of notes.txt",
    "search this folder for the phrase violet glow", "copy the file to my Desktop",
    "move the file into the archive folder", "create a new folder called archive",
    "delete the file and send it to the recycle bin", "show me the file size and metadata",
    "launch Blender", "What is the capital of France?", "confirmed", "you're authorized to do it",
    "list me the tools you have", "Maak nog een exemplaar",
))
def test_visible_catalog_is_independent_of_request_wording(user_text):
    assert select_turn_capabilities(user_text, CATALOG) == CATALOG


def test_explicit_tool_name_cannot_enable_a_disabled_tool():
    available = ("filesystem.stat", "filesystem.write_text")
    assert select_turn_capabilities("Use filesystem.trash exactly once.", available) == available


@pytest.mark.parametrize(("text", "catalog", "error"), (
    (None, CATALOG, TypeError), ("hello", (), ValueError),
    ("hello", ("filesystem.stat", "filesystem.stat"), ValueError),
))
def test_catalog_rejects_invalid_inputs(text, catalog, error):
    with pytest.raises(error):
        select_turn_capabilities(text, catalog)
