from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.settings.loader import load_json
from app.settings.paths import PATHS


class CloudConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str = "OpenRouter Free"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    fallback_models: tuple[str, ...] = Field(default_factory=tuple, max_length=7)
    api_key_environment: str = "OPENROUTER_API_KEY"
    context_length: int = Field(32768, ge=1024)
    temperature: float = Field(0.1, ge=0, le=2)
    max_tokens: int = Field(512, ge=32)
    timeout_seconds: int = Field(90, ge=5, le=300)
    default_mode: Literal["local", "cloud"] = "local"
    fallback_to_local: bool = True
    extra_headers: dict[str, str] = Field(default_factory=dict)
    include_tool_strict: bool = True
    tool_choice: Literal["auto", "none", "required"] | None = "auto"

    @field_validator("provider_name", "model", "api_key_environment")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be empty.")
        return value

    @field_validator("fallback_models")
    @classmethod
    def validate_fallback_models(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(value.strip() for value in values)
        if any(not value for value in cleaned):
            raise ValueError("fallback_models must not contain empty model IDs.")
        if any(any(character.isspace() for character in value) for value in cleaned):
            raise ValueError("Cloud model IDs must not contain whitespace.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("fallback_models must not contain duplicate model IDs.")
        return cleaned

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

    @model_validator(mode="after")
    def validate_extra_headers(self):
        cleaned: dict[str, str] = {}
        forbidden = {
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "api-key",
        }
        header_name = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
        for raw_name, raw_value in self.extra_headers.items():
            if not isinstance(raw_name, str) or not isinstance(raw_value, str):
                raise ValueError("Cloud extra_headers must contain string names and values.")
            name = raw_name.strip()
            value = raw_value.strip()
            if not name or header_name.fullmatch(name) is None:
                raise ValueError("Cloud extra_headers contains an invalid header name.")
            if name.casefold() in forbidden:
                raise ValueError("Cloud extra_headers must not contain credentials.")
            if not value or "\r" in value or "\n" in value:
                raise ValueError("Cloud extra_headers contains an invalid header value.")
            cleaned[name] = value
        object.__setattr__(self, "extra_headers", cleaned)
        return self

    @model_validator(mode="after")
    def validate_model_pool(self):
        if any(character.isspace() for character in self.model):
            raise ValueError("Cloud model IDs must not contain whitespace.")
        if self.model in self.fallback_models:
            raise ValueError("The primary cloud model cannot also be a fallback model.")
        return self

    @property
    def model_pool(self) -> tuple[str, ...]:
        return (self.model, *self.fallback_models)

    @property
    def chat_completions_url(self) -> str:
        if self.base_url.casefold().endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"


def load_cloud_config() -> CloudConfig:
    return CloudConfig.model_validate(load_json(PATHS.config / "cloud.json", default={}))
