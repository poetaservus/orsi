from __future__ import annotations

import pytest

from app.conversation.capability_routing import select_turn_capabilities


CATALOG = (
    "application.launch",
    "filesystem.copy",
    "filesystem.find",
    "filesystem.list",
    "filesystem.mkdir",
    "filesystem.move",
    "filesystem.read_text",
    "filesystem.search",
    "filesystem.stat",
    "filesystem.trash",
    "filesystem.write_text",
)


@pytest.mark.parametrize(
    ("user_text", "expected"),
    (
        (
            "edit style.css and give it a sleek charcoal and violet design",
            (
                "filesystem.list",
                "filesystem.read_text",
                "filesystem.stat",
                "filesystem.write_text",
            ),
        ),
        (
            "what's in my Documents website folder?",
            ("filesystem.list", "filesystem.stat"),
        ),
        (
            "read the contents of notes.txt",
            (
                "filesystem.list",
                "filesystem.read_text",
                "filesystem.stat",
            ),
        ),
        ("search this folder for the phrase violet glow", ("filesystem.search", "filesystem.stat")),
        (
            "copy the file to my Desktop",
            ("filesystem.copy", "filesystem.stat"),
        ),
        (
            "move the file into the archive folder",
            ("filesystem.move", "filesystem.stat"),
        ),
        (
            "create a new folder called archive",
            ("filesystem.mkdir", "filesystem.stat"),
        ),
        (
            "delete the file and send it to the recycle bin",
            ("filesystem.stat", "filesystem.trash"),
        ),
        ("show me the file size and metadata", ("filesystem.stat",)),
        ("launch Blender", ("application.launch", "filesystem.stat")),
        ("What is the capital of France?", ("filesystem.stat",)),
    ),
)
def test_turn_router_advertises_only_relevant_capabilities(user_text, expected):
    assert select_turn_capabilities(user_text, CATALOG) == expected


def test_explicit_capability_name_is_honored_when_enabled():
    assert select_turn_capabilities(
        "Use filesystem.write_text exactly once.",
        CATALOG,
    ) == (
        "filesystem.list",
        "filesystem.read_text",
        "filesystem.stat",
        "filesystem.write_text",
    )


def test_turn_router_never_returns_disabled_dependencies():
    available = ("filesystem.stat", "filesystem.write_text")
    assert select_turn_capabilities("edit style.css", available) == available


@pytest.mark.parametrize(
    ("text", "catalog", "error"),
    (
        (None, CATALOG, TypeError),
        ("hello", (), ValueError),
        ("hello", ("filesystem.stat", "filesystem.stat"), ValueError),
    ),
)
def test_turn_router_rejects_invalid_inputs(text, catalog, error):
    with pytest.raises(error):
        select_turn_capabilities(text, catalog)
