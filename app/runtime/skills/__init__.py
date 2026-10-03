"""Public instruction-only skill parsing, loading, discovery and registry API."""
from app.runtime.skills.contracts import (
    SkillDefinition, SkillDiscoveryIssue, SkillDiscoveryReport,
    SkillLoadError, SkillLoadErrorCode, SkillParseError, SkillParseErrorCode,
)
from app.runtime.skills.discovery import MAX_DISCOVERY_ENTRIES, discover_skills
from app.runtime.skills.loader import MAX_SKILL_SIZE, load_skill
from app.runtime.skills.parser import parse_skill
from app.runtime.skills.registry import SkillRegistry
from app.runtime.skills.activation import SkillActivationError, SkillActivationErrorCode, with_active_skill
from app.runtime.skills.selection import SkillCandidate, SkillSelection, select_skill

__all__ = [
    "SkillDefinition", "SkillLoadError", "SkillLoadErrorCode", "SkillParseError", "SkillParseErrorCode",
    "MAX_SKILL_SIZE", "load_skill", "parse_skill",
    "SkillDiscoveryIssue", "SkillDiscoveryReport", "MAX_DISCOVERY_ENTRIES", "discover_skills",
    "SkillRegistry",
    "SkillActivationError", "SkillActivationErrorCode", "with_active_skill",
    "SkillCandidate", "SkillSelection", "select_skill",
]
