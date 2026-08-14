from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict

from app.config import load_json
from app.paths import PATHS


_ENVIRONMENT_GATE = "ORSI_ENABLE_FILESYSTEM_STAT"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class AgentFeatureConfig(BaseModel):
    """Fail-closed Phase 8 gate for the sole production capability."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    filesystem_stat_enabled: bool = False


def load_agent_feature_config() -> AgentFeatureConfig:
    config = AgentFeatureConfig.model_validate(
        load_json(PATHS.config / "agent.json", default={})
    )
    override = os.environ.get(_ENVIRONMENT_GATE)
    if override is None:
        return config
    normalized = override.strip().casefold()
    if normalized in _TRUE_VALUES:
        enabled = True
    elif normalized in _FALSE_VALUES:
        enabled = False
    else:
        raise ValueError(
            f"{_ENVIRONMENT_GATE} must be an explicit true or false value."
        )
    return config.model_copy(update={"filesystem_stat_enabled": enabled})
