"""File-backed conversational styles; operational authority stays in prompt.py."""
from dataclasses import dataclass, field
import logging
from pathlib import Path
import re

import yaml
from yaml.nodes import MappingNode, ScalarNode


log = logging.getLogger(__name__)
PERSONALITY_DIRECTORY = Path(__file__).with_name("personalities")
MAX_PERSONALITY_BYTES = 32_768
_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class Personality:
    id: str
    name: str
    version: str | None = None

    description: str = ""
    guidance: str = field(default="", repr=False)


def load_personality(source: Path) -> Personality:
    """Read bounded UTF-8 Markdown/text with flat YAML metadata and a style body."""
    with source.open("rb") as stream:
        raw = stream.read(MAX_PERSONALITY_BYTES + 1)
    if len(raw) > MAX_PERSONALITY_BYTES:
        raise ValueError("The personality file exceeds 32 KiB.")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("The personality file requires YAML frontmatter.")
    header, separator, body = text[4:].partition("\n---\n")
    if not separator or not body.strip():
        raise ValueError("The personality file requires a non-empty style body.")
    try:
        node = yaml.compose(header, Loader=yaml.BaseLoader)
    except (yaml.YAMLError, RecursionError):
        raise ValueError("The personality metadata is invalid.") from None
    if not isinstance(node, MappingNode):
        raise ValueError("The personality metadata must be a flat mapping.")
    metadata = {}
    for key, value in node.value:
        if (not isinstance(key, ScalarNode) or not isinstance(value, ScalarNode)
                or key.value in metadata):
            raise ValueError("The personality metadata requires unique scalar fields.")
        metadata[key.value] = value.value
    personality_id = metadata.get("id", source.stem)
    name = metadata.get("name", "")
    if (len(personality_id) > 64 or not _ID.fullmatch(personality_id)
            or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name)
            or metadata.get("type", "personality") != "personality"):
        raise ValueError("The personality requires a stable ID, name and personality type.")
    description = metadata.get("description", "")
    version = metadata.get("version") or None
    if len(description) > 512 or version is not None and len(version) > 80:
        raise ValueError("The personality metadata is too long.")
    return Personality(personality_id, name.strip(), version, description, body.strip())


def discover_personalities(directory: Path = PERSONALITY_DIRECTORY) -> tuple[Personality, ...]:
    """Discover on startup; malformed additions never displace existing definitions."""
    result = {}
    # Reserve the bundled identities before considering additional files.
    sources = sorted(directory.iterdir(), key=lambda p: (p.name not in {"original.md", "choom.md"}, p.name.lower()))
    for source in sources:
        if source.suffix.lower() not in {".md", ".txt"} or not source.is_file():
            continue
        try:
            personality = load_personality(source)
            if personality.id in result:
                raise ValueError("Duplicate personality ID.")
        except (OSError, ValueError):
            log.warning("A personality file was skipped; check its metadata, UTF-8 encoding and size.")
            continue
        result[personality.id] = personality
    return tuple(sorted(result.values(), key=lambda p: (p.id != "original", p.name.casefold(), p.id)))


PERSONALITIES = discover_personalities()


def get_personality(personality_id: str) -> Personality:
    # Resolve existing saved preferences without rewriting their private storage.
    if personality_id == "choom-v1.0.0":
        personality_id = "choom"
    for personality in PERSONALITIES:
        if personality.id == personality_id:
            return personality
    raise ValueError("The selected personality is unavailable.")


# Compatibility for callers measuring the default voice. Core prompts never use it.
PERSONALITY_GUIDANCE = get_personality("original").guidance


def with_personality(prompt: str, personality: Personality) -> str:
    """Compose a personality-free operational prompt with exactly one selected style."""
    if "\n\nSELECTED PERSONALITY (style only)\n" in prompt:
        raise ValueError("The response prompt already contains a personality.")
    return prompt + "\n\nSELECTED PERSONALITY (style only)\n" + personality.guidance
