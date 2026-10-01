"""Versioned model targets; runtime selection never writes this configuration."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.settings.loader import load_json
from app.settings.model import ModelConfig


class LocalModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.gguf$", max_length=128)
    qualification: Literal["accepted", "load_tested", "experimental", "unqualified"]
    architecture: Literal["qwen2", "qwen3", "qwen3vl"]
    size_bytes: int | None = Field(default=None, gt=0)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    cpu_max_tokens: int = Field(default=1024, ge=32)
    configuration: ModelConfig

    @model_validator(mode="after")
    def validate_target(self):
        if Path(self.configuration.model_path).name != self.model_id:
            raise ValueError("The profile ID must match its model filename.")
        if not isinstance(self.configuration.context_length, int):
            raise ValueError("Versioned profiles require an explicit target context.")
        if self.configuration.context_length < 512:
            raise ValueError("The target context is too small.")
        if not self.configuration.minimum_context_length <= self.configuration.context_length <= self.configuration.maximum_context_length:
            raise ValueError("The target context must fit the profile's minimum and maximum.")
        if self.qualification in {"accepted", "load_tested"} and (self.sha256 is None or self.size_bytes is None):
            raise ValueError("Qualified profiles require the model size and SHA-256 identity.")
        if self.configuration.max_tokens > self.configuration.context_length // 2:
            raise ValueError("The target reply reserve cannot exceed half the context.")
        if self.cpu_max_tokens > self.configuration.cpu_context_length // 2:
            raise ValueError("The CPU reply reserve cannot exceed half the context.")
        return self


class LocalModelProfiles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    default_model_id: str
    profiles: tuple[LocalModelProfile, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_catalog(self):
        ids = [profile.model_id for profile in self.profiles]
        if len(set(ids)) != len(ids) or self.default_model_id not in ids:
            raise ValueError("Profiles need unique IDs and an existing default.")
        return self

    def get(self, model_id: str) -> LocalModelProfile | None:
        return next((profile for profile in self.profiles if profile.model_id == model_id), None)


def load_model_profiles(path: Path) -> LocalModelProfiles:
    return LocalModelProfiles.model_validate(load_json(path))
