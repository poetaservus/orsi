"""Deterministic parsers used only by scripted model doubles in tests.

Production tool selection is model-first and does not import this module.
"""

from __future__ import annotations

from pathlib import Path
import re


_FOLDER_REQUEST = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:(?:create|make)\s+(?:(?:a|an|new|empty)\s+)*(?:folder|directory)\b"
    r"|(?:filesystem[.]mkdir|mkdir)\b)",
    re.I,
)
_COPY_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:filesystem[.]copy|copy)\b",
    re.I,
)
_MOVE_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:filesystem[.]move|move)\b",
    re.I,
)
_TRASH_START = re.compile(
    r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+|you\s+can\s+)?"
    r"(?:filesystem[.]trash|trash|recycle|delete)\b",
    re.I,
)


def folder_creation_target(text: str) -> str | None:
    match = _FOLDER_REQUEST.match(text.strip())
    if match is None:
        return None
    remainder = text.strip()[match.end():].strip()
    remainder = re.sub(r"^(?:at path|at)\s+", "", remainder, flags=re.I)
    if remainder.startswith(('"', "'")):
        quote = remainder[0]
        if len(remainder) < 3 or remainder[-1] != quote:
            return None
        remainder = remainder[1:-1]
    return _absolute_path_argument(remainder)


def text_write_request(text: str) -> tuple[str, str] | None:
    value = str(text).strip()
    first_line, separator, content = value.partition("\n")
    if separator:
        match = re.match(
            r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:write|save)\s+"
            r"(?:(?:the|this|following|exact)\s+)?(?:text|content|file)\s+to\s+(.+):\s*\Z",
            first_line.strip(),
            re.I,
        )
        if match is not None:
            path = _absolute_path_argument(match.group(1))
            if path is not None:
                return path, content
    match = re.match(
        r"\A(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:write|save)\s+"
        r"(?:(?:text|content)\s+)?(?P<quote>[\"'])(?P<content>.*)(?P=quote)\s+to\s+(?P<path>.+)\Z",
        value,
        re.I | re.S,
    )
    if match is not None:
        path = _absolute_path_argument(match.group("path"))
        if path is not None:
            return path, match.group("content")
    match = re.match(
        r"\Afilesystem[.]write_text\s+(?P<path>(?:\"[^\"]+\"|'[^']+'|[A-Za-z]:[^\r\n]+?))\s+"
        r"(?P<quote>[\"'])(?P<content>.*)(?P=quote)\Z",
        value,
        re.I | re.S,
    )
    if match is not None:
        path = _absolute_path_argument(match.group("path"))
        if path is not None:
            return path, match.group("content")
    return None


def copy_request(text: str) -> tuple[str, str, str] | None:
    return _two_path_request(text, _COPY_START)


def move_request(text: str) -> tuple[str, str, str] | None:
    return _two_path_request(text, _MOVE_START)


def _two_path_request(text: str, prefix: re.Pattern[str]) -> tuple[str, str, str] | None:
    value = str(text).strip()
    match = prefix.match(value)
    if match is None:
        return None
    remainder = re.sub(
        r"^(?:file\s+)?(?:from\s+)?",
        "",
        value[match.end():].strip(),
        flags=re.I,
    )
    parts = re.split(r"\s+to\s+", remainder, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None
    source = _absolute_path_argument(parts[0])
    destination_text = parts[1].strip()
    collision = "fail"
    policy = re.search(
        r"\s+(?:(?:with\s+)?(?:replace|overwrite)(?:\s+existing(?:\s+file)?)?"
        r"|replacing\s+existing(?:\s+file)?)\s*\Z",
        destination_text,
        re.I,
    )
    if policy is not None:
        collision = "replace"
        destination_text = destination_text[:policy.start()].strip()
    destination = _absolute_path_argument(destination_text)
    if source is None or destination is None:
        return None
    return source, destination, collision


def trash_target(text: str) -> str | None:
    value = str(text).strip()
    match = _TRASH_START.match(value)
    if match is None:
        return None
    lowered = " ".join(value.casefold().split())
    if re.search(
        r"\b(?:permanently\s+delete|delete\s+permanently|remove\s+permanently)\b",
        lowered,
    ):
        return None
    remainder = re.sub(
        r"^(?:file\s+)?(?:at\s+)?(?:path\s+)?",
        "",
        value[match.end():].strip(),
        flags=re.I,
    )
    return _absolute_path_argument(remainder)


def explicit_windows_path(text: str) -> str | None:
    value = str(text)
    quoted = re.search(r"[\"']([A-Za-z]:[\\/][^\"']+)[\"']", value)
    if quoted is not None:
        return quoted.group(1).strip()
    unquoted = re.search(r"(?i)([a-z]:[\\/].+)$", value)
    if unquoted is None:
        return None
    candidate = re.split(
        r"(?i)\s+(?:and\s+(?:report|show|tell|list|give)|then|please)\b",
        unquoted.group(1),
        maxsplit=1,
    )[0].strip().rstrip("?!.,;:\"'")
    return candidate or None


def is_listing_request(lowered: str) -> bool:
    return bool(
        re.search(r"\bfilesystem[.]list\b", lowered)
        or re.search(r"\b(?:check\s+)?what\s+(?:do\s+)?(?:i|we)\s+have\s+(?:in|inside|under)\b", lowered)
        or re.search(r"\b(?:n[eé]zd\s+meg[,.]?\s*)?mi(?:k)?\s+(?:van|vannak)\b", lowered)
        or re.search(r"\b(?:list|show|display)\b.{0,80}\b(?:files?|folders?|director(?:y|ies)|entries|contents|items)\b", lowered)
        or re.search(r"\b(?:what|which)\s+(?:files?|folders?|directories|entries|items)\b", lowered)
        or re.search(r"\b(?:files?|folders?|directories|entries|items)\s+(?:do\s+i\s+have|are\s+(?:in|inside|under|there))\b", lowered)
        or re.search(r"\b(?:contents|entries)\s+(?:of|in|inside)\b", lowered)
        or re.search(r"\bwhat(?:'s|\s+is)\s+(?:in|inside)\s+(?:it|there|that|this)\b", lowered)
        or re.search(r"\b(?:check\s+)?what(?:'s|\s+is)\s+(?:in|inside|under)\b", lowered)
        or re.search(r"\bwhat\s+(?:files?|folders?|directories|entries|items)\s+(?:i|we)\s+have\s+(?:there|in\s+it|inside\s+it)\b", lowered)
        or re.search(r"\b(?:show\s+me\s+)?what\s+is\s+in\b", lowered)
    )


def find_target(text: str, host_access_policy) -> tuple[str, str, str] | None:
    value = str(text).strip()
    lowered = " ".join(value.casefold().split())
    if not _is_find_name_request(lowered):
        return None
    name = _find_requested_name(value)
    path = find_base_path(value, host_access_policy)
    if not name or path is None:
        return None
    kind = "directory" if re.search(r"\b(?:folders?|directories|directory)\b", lowered) else (
        "file" if re.search(r"\b(?:files?|documents?)\b", lowered) else "any"
    )
    return str(path), name, kind


def find_base_path(value: str, host_access_policy) -> Path | None:
    explicit = explicit_windows_path(value)
    if explicit is not None:
        return Path(explicit)
    alias = _known_folder_alias(value)
    user_home = getattr(host_access_policy, "user_home", None)
    if alias is None or not isinstance(user_home, Path):
        return None
    return user_home if alias == "home" else user_home / alias


def search_target_and_query(text: str) -> tuple[str, str] | None:
    value = str(text).strip()
    quoted_path = re.search(r"[\"']([A-Za-z]:[\\/][^\"']+)[\"']", value)
    if quoted_path is not None:
        path = quoted_path.group(1).strip()
        for match in re.finditer(r"[\"']([^\"']+)[\"']", value):
            candidate = match.group(1).strip()
            if candidate.casefold() != path.casefold() and not re.match(r"(?i)^[a-z]:[\\/]", candidate):
                return path, _clean_query(candidate)
    path_then_query = re.search(
        r"(?is)\b(?:search|find)\b\s+([a-z]:[\\/].+?)\s+\b(?:for|containing|matching)\s+(.+)$",
        value,
    )
    if path_then_query is not None:
        return path_then_query.group(1).strip().rstrip("?!.,;:\"'"), _clean_query(path_then_query.group(2))
    query_then_path = re.search(
        r"(?is)\b(?:search|find|look\s+for)\b(?:\s+for)?\s+(.+?)\s+\b(?:in|inside|under|within)\s+([a-z]:[\\/].+)$",
        value,
    )
    if query_then_path is not None:
        return query_then_path.group(2).strip().rstrip("?!.,;:\"'"), _clean_query(query_then_path.group(1))
    return None


def _absolute_path_argument(raw: str) -> str | None:
    value = str(raw).strip()
    if value.startswith(('"', "'")):
        quote = value[0]
        if len(value) < 3 or value[-1] != quote:
            return None
        value = value[1:-1]
    if (
        not re.fullmatch(r"[A-Za-z]:[\\/].+", value)
        or re.search(r"[\r\n\"']|\s+(?:and|then)\s+", value, re.I)
        or len(re.findall(r"[A-Za-z]:[\\/]", value)) != 1
    ):
        return None
    return value


def _is_find_name_request(lowered: str) -> bool:
    return bool(
        re.search(r"\bfilesystem[.]find\b", lowered)
        or (
            re.search(r"\b(?:called|named)\b", lowered)
            and re.search(r"\b(?:find|locate|where|folder|directory|file|document)\b", lowered)
        )
        or re.search(r"\b(?:find|locate)\b.{0,60}\b(?:folder|directory|file|document)\b", lowered)
    )


def _find_requested_name(value: str) -> str | None:
    patterns = (
        r"(?is)\b(?:called|named)\s+[\"']([^\"'\\/\r\n]+)[\"']",
        r"(?is)\b(?:called|named)\s+([^,;?!\\/\r\n]+)",
        r"(?is)\b(?:folder|directory|file|document)\s+[\"']([^\"'\\/\r\n]+)[\"']",
        r"(?is)\b(?:find|locate)\s+(?:the\s+)?(?:folder|directory|file|document)\s+([^,;?!\\/\r\n]+?)\s+\b(?:on|in|inside|under)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match is None:
            continue
        name = _clean_find_name(match.group(1))
        if name:
            return name
    return None


def _clean_find_name(value: str) -> str:
    name = str(value).strip().strip("\"'").strip()
    for pattern in (
        r"(?is)\s+\b(?:find|locate)\s+it\b.*$",
        r"(?is)\s+\b(?:can|could|would)\s+you\b.*$",
        r"(?is)\s+\b(?:please\s+)?(?:check|list|show|display|tell|what(?:'s|\s+is))\b.*$",
        r"(?is)\s+\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?(?:desktop|downloads|documents|home)(?:\s+(?:folder|directory))?\b.*$",
    ):
        name = re.sub(pattern, "", name).strip()
    name = re.sub(r"(?is)^(?:a|an|the)\s+", "", name).rstrip(".").strip()
    if not name or len(name) > 255 or "\x00" in name or any(s in name for s in ("/", "\\")) or name in {".", ".."}:
        return ""
    return name


def _known_folder_alias(value: str) -> str | None:
    lowered = " ".join(str(value).casefold().split())
    checks = (
        (r"\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?desktop(?:\s+folder)?\b|\b(?:az\s+)?asztal(?:om)?(?:on)?\b", "Desktop"),
        (r"\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?downloads(?:\s+folder)?\b|\b(?:a\s+)?let[oö]lt[eé]s(?:ek|eim)?(?:ben)?\b", "Downloads"),
        (r"\b(?:on|in|inside|under)\s+(?:my\s+|the\s+)?documents(?:\s+folder)?\b|\b(?:a\s+)?dokumentum(?:ok|aim)?(?:ban|ben)?\b", "Documents"),
        (r"\b(?:in|inside|under)\s+(?:my\s+)?home(?:\s+folder|\s+directory)?\b", "home"),
    )
    return next((alias for pattern, alias in checks if re.search(pattern, lowered)), None)


def _clean_query(value: str) -> str:
    query = str(value).strip().strip("\"'").strip().rstrip("?!.,;")
    query = re.sub(r"(?i)^(?:literal\s+)?(?:text|phrase|string)\s+", "", query).strip()
    return "" if "\x00" in query or len(query) > 512 else query
