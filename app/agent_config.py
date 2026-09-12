from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, model_validator

from app.config import load_json
from app.paths import PATHS


_FILESYSTEM_STAT_GATE = "ORSI_ENABLE_FILESYSTEM_STAT"
_FILESYSTEM_LIST_GATE = "ORSI_ENABLE_FILESYSTEM_LIST"
_FILESYSTEM_READ_TEXT_GATE = "ORSI_ENABLE_FILESYSTEM_READ_TEXT"
_FULL_LOCAL_READ_GATE = "ORSI_ENABLE_FULL_LOCAL_READ"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class AgentFeatureConfig(BaseModel):
    """Fail-closed gates for the current production capability and its read scope."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    filesystem_stat_enabled: bool = False
    filesystem_list_enabled: bool = False
    filesystem_read_text_enabled: bool = False
    full_local_read_enabled: bool = False

    @model_validator(mode="after")
    def validate_feature_dependencies(self):
        if self.filesystem_list_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Directory listing requires the filesystem metadata agent."
            )
        if self.filesystem_read_text_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Text-file reading requires the filesystem metadata agent."
            )
        if self.full_local_read_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Full local read access requires the filesystem metadata agent."
            )
        return self


def load_agent_feature_config() -> AgentFeatureConfig:
    values = load_json(PATHS.config / "agent.json", default={})
    if not isinstance(values, dict):
        raise ValueError("Agent feature configuration must be a JSON object.")
    values = dict(values)
    for name, field in (
        (_FILESYSTEM_STAT_GATE, "filesystem_stat_enabled"),
        (_FILESYSTEM_LIST_GATE, "filesystem_list_enabled"),
        (_FILESYSTEM_READ_TEXT_GATE, "filesystem_read_text_enabled"),
        (_FULL_LOCAL_READ_GATE, "full_local_read_enabled"),
    ):
        override = os.environ.get(name)
        if override is not None:
            values[field] = _parse_environment_boolean(name, override)
    return AgentFeatureConfig.model_validate(values)


def _parse_environment_boolean(name: str, override: str) -> bool:
    if override is None:
        raise TypeError("Environment boolean overrides must be strings.")
    normalized = override.strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be an explicit true or false value.")
