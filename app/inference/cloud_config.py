from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import load_json
from app.paths import PATHS


class CloudConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str = "OpenRouter Free"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openrouter/free"
    api_key_environment: str = "OPENROUTER_API_KEY"
    context_length: int = Field(32768, ge=1024)
    temperature: float = Field(0.1, ge=0, le=2)
    max_tokens: int = Field(512, ge=32)
    timeout_seconds: int = Field(90, ge=5, le=300)
    default_mode: Literal["local", "cloud"] = "local"
    fallback_to_local: bool = True

    @field_validator("provider_name", "model", "api_key_environment")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be empty.")
        return value

    @field_validator("api_key_environment")
    @classmethod
    def validate_environment_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("api_key_environment must be an environment-variable name.")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_secure_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme.casefold() != "https" or not parsed.netloc:
            raise ValueError("Cloud inference requires an HTTPS base_url.")
        return value

    @property
    def chat_completions_url(self) -> str:
        if self.base_url.casefold().endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"


def load_cloud_config() -> CloudConfig:
    return CloudConfig.model_validate(load_json(PATHS.config / "cloud.json", default={}))
