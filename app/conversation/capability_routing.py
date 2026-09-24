from __future__ import annotations

import re


_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "filesystem.stat": (
        re.compile(r"\b(?:metadata|properties|file size|folder size|directory size|exists?)\b"),
        re.compile(r"\binspect\b.*\b(?:file|folder|directory|path)\b"),
    ),
    "filesystem.find": (
        re.compile(r"\b(?:find|locate)\b"),
        re.compile(
            r"\b(?:there\s+is|i\s+have|i(?:'ve|\s+have)\s+got)\b.*"
            r"\b(?:file|folder|directory)\b.*\b(?:called|named)\b"
        ),
    ),
    "filesystem.list": (
        re.compile(r"\blist\b"),
        re.compile(r"\b(?:list|browse)\b.*\b(?:files?|folder|directory|contents?)\b"),
        re.compile(r"\bwhat(?:'s| is)\s+(?:in|inside)\b"),
        re.compile(r"\bwhat\s+files?\b.*\b(?:in|at|there)\b"),
        re.compile(r"\bwhat\s+files?\s+(?:do\s+)?i\s+have\b"),
        re.compile(r"\b(?:check|show)\b.*\bwhat\s+i\s+have\s+in\b"),
        re.compile(r"\bmi\s+van\b.*\bdokument"),
        re.compile(r"\b(?:folder|directory)\s+contents?\b"),
    ),
    "filesystem.read_text": (
        re.compile(r"\bread\b"),
        re.compile(r"\b(?:read|summari[sz]e|explain)\b.*\b(?:file|text|contents?)\b"),
        re.compile(r"\b(?:show|display|view)\b.*\b(?:text|contents?)\b"),
        re.compile(
            r"\b(?:read|show|display|view|summari[sz]e|explain)\b.*"
            r"\.(?:css|html?|js|json|md|txt|py|toml|ya?ml)\b"
        ),
    ),
    "filesystem.search": (
        re.compile(r"\b(?:search|grep)\b"),
        re.compile(r"\bfind\b.*\b(?:text|word|string|phrase|occurrence|inside|within)\b"),
    ),
    "filesystem.mkdir": (
        re.compile(r"\bmkdir\b"),
        re.compile(r"\b(?:create|make|new)\b.*\b(?:folder|directory)\b"),
    ),
    "filesystem.write_text": (
        re.compile(r"\b(?:write|edit|modify|update|rewrite|replace|restyle|redesign)\b"),
        re.compile(r"\b(?:make|change)\b.*\b(?:file|text|css|html|javascript|design|style|theme|color)\b"),
    ),
    "filesystem.copy": (
        re.compile(r"\b(?:copy|duplicate)\b"),
    ),
    "filesystem.move": (
        re.compile(r"\b(?:move|rename)\b"),
    ),
    "filesystem.trash": (
        re.compile(r"\b(?:trash|delete|recycle|remove)\b"),
    ),
    "application.launch": (
        re.compile(r"\b(?:open|launch|start|run|fire\s+up)\b.*\bblender\b"),
    ),
}

_EDIT_EXISTING = re.compile(
    r"\b(?:edit|modify|update|rewrite|replace|restyle|redesign|change)\b"
)


def select_turn_capabilities(
    latest_user_text: str,
    available_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return a small deterministic tool catalog for one user turn.

    Routing only limits what the model can see. The registry, permission gate,
    approval flow, and argument validation remain authoritative.
    """
    if not isinstance(latest_user_text, str):
        raise TypeError("Capability routing requires the latest user text.")
    if (
        not isinstance(available_names, tuple)
        or not available_names
        or not all(isinstance(name, str) and name for name in available_names)
        or len(set(available_names)) != len(available_names)
    ):
        raise ValueError("Capability routing requires a non-empty unique catalog.")

    text = latest_user_text.casefold()
    selected: set[str] = set()
    available = set(available_names)

    # Explicit capability names are useful for diagnostics and acceptance tests.
    for name in available_names:
        if name.casefold() in text:
            selected.add(name)

    for name, patterns in _PATTERNS.items():
        if name in available and any(pattern.search(text) for pattern in patterns):
            selected.add(name)

    # Editing an existing text file is a read/transform/write operation. Expose
    # both halves from the start so the same bounded agent run can continue.
    if (
        "filesystem.write_text" in selected
        and _EDIT_EXISTING.search(text)
        and "filesystem.read_text" in available
    ):
        selected.add("filesystem.read_text")

    # Path resolution and same-folder filename disambiguation may require a
    # short read-only chain before the requested operation can run.
    dependency_names: set[str] = set()
    if selected & {"filesystem.read_text", "filesystem.write_text"}:
        dependency_names.add("filesystem.list")
    if "filesystem.write_text" in selected:
        dependency_names.add("filesystem.read_text")
    selected.update(dependency_names & available)

    # Keep ordinary conversation on the smallest safe catalog. This preserves
    # the existing agent path without paying for every schema on every turn.
    if not selected:
        fallback = (
            "filesystem.stat" if "filesystem.stat" in available else available_names[0]
        )
        selected.add(fallback)

    # The established agent prompt and path-resolution policy use stat as the
    # small, read-only safety baseline for every scoped catalog.
    if "filesystem.stat" in available:
        selected.add("filesystem.stat")

    return tuple(name for name in available_names if name in selected)
