from __future__ import annotations

import math
import os

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.settings.loader import load_json
from app.settings.paths import PATHS


_FILESYSTEM_STAT_GATE = "ORSI_ENABLE_FILESYSTEM_STAT"
_FILESYSTEM_FIND_GATE = "ORSI_ENABLE_FILESYSTEM_FIND"
_FILESYSTEM_LIST_GATE = "ORSI_ENABLE_FILESYSTEM_LIST"
_FILESYSTEM_READ_TEXT_GATE = "ORSI_ENABLE_FILESYSTEM_READ_TEXT"
_FILESYSTEM_SEARCH_GATE = "ORSI_ENABLE_FILESYSTEM_SEARCH"
_FILESYSTEM_MKDIR_GATE = "ORSI_ENABLE_FILESYSTEM_MKDIR"
_FILESYSTEM_WRITE_TEXT_GATE = "ORSI_ENABLE_FILESYSTEM_WRITE_TEXT"
_FILESYSTEM_COPY_GATE = "ORSI_ENABLE_FILESYSTEM_COPY"
_FILESYSTEM_MOVE_GATE = "ORSI_ENABLE_FILESYSTEM_MOVE"
_FILESYSTEM_TRASH_GATE = "ORSI_ENABLE_FILESYSTEM_TRASH"
_APPLICATION_LAUNCH_GATE = "ORSI_ENABLE_APPLICATION_LAUNCH"
_FULL_LOCAL_READ_GATE = "ORSI_ENABLE_FULL_LOCAL_READ"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class AgentRuntimeLimits(BaseModel):
    """Serializable limits for the bounded agent loop."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_steps: int = Field(default=24, ge=1, le=32)
    max_capability_calls: int = Field(default=32, ge=1, le=32)
    max_identical_calls: int = Field(default=2, ge=1, le=8)
    max_protocol_failures: int = Field(default=2, ge=1, le=8)
    overall_timeout_seconds: float | None = Field(default=None, gt=0, le=3_600)
    poll_interval_seconds: float = Field(default=0.01, gt=0, le=1.0)
    max_transcript_bytes: int = Field(
        default=4 * 1024 * 1024,
        ge=1_024,
        le=16 * 1024 * 1024,
    )

    @model_validator(mode="after")
    def validate_finite_durations(self):
        if (
            self.overall_timeout_seconds is not None
            and not math.isfinite(self.overall_timeout_seconds)
        ):
            raise ValueError("The runtime timeout must be finite.")
        if not math.isfinite(self.poll_interval_seconds):
            raise ValueError("The runtime polling interval must be finite.")
        return self


class AgentFeatureConfig(BaseModel):
    """Fail-closed capability gates plus bounded agent-loop configuration."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    filesystem_stat_enabled: bool = False
    filesystem_find_enabled: bool = False
    filesystem_list_enabled: bool = False
    filesystem_read_text_enabled: bool = False
    filesystem_search_enabled: bool = False
    filesystem_mkdir_enabled: bool = False
    filesystem_write_text_enabled: bool = False
    filesystem_copy_enabled: bool = False
    filesystem_move_enabled: bool = False
    filesystem_trash_enabled: bool = False
    application_launch_enabled: bool = False
    full_local_read_enabled: bool = False
    runtime_limits: AgentRuntimeLimits = Field(default_factory=AgentRuntimeLimits)

    @model_validator(mode="after")
    def validate_feature_dependencies(self):
        if self.filesystem_find_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Filesystem name lookup requires the filesystem metadata agent."
            )
        if self.filesystem_mkdir_enabled and not self.filesystem_stat_enabled:
            raise ValueError("Folder creation requires the filesystem metadata agent.")
        if self.filesystem_write_text_enabled and not self.filesystem_stat_enabled:
            raise ValueError("Text writing requires the filesystem metadata agent.")
        if self.filesystem_copy_enabled and not self.filesystem_stat_enabled:
            raise ValueError("File copying requires the filesystem metadata agent.")
        if self.filesystem_move_enabled and not self.filesystem_stat_enabled:
            raise ValueError("File moving requires the filesystem metadata agent.")
        if self.filesystem_trash_enabled and not self.filesystem_stat_enabled:
            raise ValueError("File trashing requires the filesystem metadata agent.")
        if self.application_launch_enabled and not self.filesystem_stat_enabled:
            raise ValueError("Application launch requires the structured capability agent.")
        if self.filesystem_list_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Directory listing requires the filesystem metadata agent."
            )
        if self.filesystem_read_text_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Text-file reading requires the filesystem metadata agent."
            )
        if self.filesystem_search_enabled and not self.filesystem_stat_enabled:
            raise ValueError(
                "Filesystem search requires the filesystem metadata agent."
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
        (_FILESYSTEM_FIND_GATE, "filesystem_find_enabled"),
        (_FILESYSTEM_LIST_GATE, "filesystem_list_enabled"),
        (_FILESYSTEM_READ_TEXT_GATE, "filesystem_read_text_enabled"),
        (_FILESYSTEM_SEARCH_GATE, "filesystem_search_enabled"),
        (_FILESYSTEM_MKDIR_GATE, "filesystem_mkdir_enabled"),
        (_FILESYSTEM_WRITE_TEXT_GATE, "filesystem_write_text_enabled"),
        (_FILESYSTEM_COPY_GATE, "filesystem_copy_enabled"),
        (_FILESYSTEM_MOVE_GATE, "filesystem_move_enabled"),
        (_FILESYSTEM_TRASH_GATE, "filesystem_trash_enabled"),
        (_APPLICATION_LAUNCH_GATE, "application_launch_enabled"),
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
