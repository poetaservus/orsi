"""Explicit OpenAI model contracts; selection is separate from versioned profiles."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.state.storage import JsonStore


ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
# Verified against the linked OpenAI model pages on 2026-10-04. These are
# documented ceilings, not a claim of account access or live qualification.
_MODEL_CONTRACTS = {
    "gpt-6-luna": (1_050_000, 128_000, {"none", "low", "medium", "high", "xhigh", "max"}),
    "gpt-6.1-sol": (1_050_000, 128_000, {"low", "medium", "high", "xhigh", "max"}),
}


class OpenAIModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    id: str
    context_length: int = Field(32_768, ge=1_024)
    max_input_tokens: int = Field(28_672, ge=1_024)
    max_output_tokens: int = Field(4_096, ge=32)
    reasoning_effort: ReasoningEffort = "none"
    temperature: float | None = Field(None, ge=0, le=2, allow_inf_nan=False)
    qualified: bool = False

    @model_validator(mode="after")
    def validate_contract(self):
        contract = _MODEL_CONTRACTS.get(self.id)
        if contract is None:
            raise ValueError("OpenAI model is not in the explicit supported profile set.")
        context, output, efforts = contract
        if self.context_length > context or self.max_output_tokens > output:
            raise ValueError("OpenAI profile exceeds documented model limits.")
        if self.max_input_tokens + self.max_output_tokens > self.context_length:
            raise ValueError("OpenAI input and output reserves exceed the context limit.")
        if self.reasoning_effort not in efforts:
            raise ValueError("The selected reasoning effort is unsupported by this model.")
        if self.reasoning_effort != "none" and self.temperature is not None:
            raise ValueError("Temperature must be omitted when reasoning is enabled.")
        return self

    @property
    def effective_context_length(self) -> int:
        return min(self.context_length, self.max_input_tokens + self.max_output_tokens)


class OpenAIRateLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    requests_per_minute: int = Field(ge=1, le=1_000_000)
    tokens_per_minute: int = Field(ge=1, le=1_000_000_000)


class OpenAIAccountRateLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    models: dict[str, OpenAIRateLimits] = Field(default_factory=dict)


class OpenAICloudConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal[2] = 2
    api: Literal["responses"] = "responses"
    provider_name: Literal["OpenAI"] = "OpenAI"
    base_url: Literal["https://api.openai.com/v1"] = "https://api.openai.com/v1"
    api_key_environment: Literal["OPENAI_API_KEY"] = "OPENAI_API_KEY"
    default_model: str = "gpt-6-luna"
    profiles: tuple[OpenAIModelProfile, ...] = Field(min_length=1, max_length=2)
    timeout_seconds: int = Field(90, ge=5, le=1800)
    max_retries: int = Field(0, ge=0, le=5)
    default_mode: Literal["local", "cloud"] = "local"
    fallback_to_local: bool = False
    rate_limits: dict[str, OpenAIRateLimits] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_profiles(self):
        ids = [profile.id for profile in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("OpenAI profiles must have unique model IDs.")
        if self.default_model not in ids:
            raise ValueError("The default OpenAI model requires an explicit profile.")
        if set(self.rate_limits) - set(ids):
            raise ValueError("Rate limits require a configured OpenAI model.")
        return self

    def profile(self, model_id: str) -> OpenAIModelProfile:
        for profile in self.profiles:
            if profile.id == model_id:
                return profile
        raise ValueError("The selected OpenAI model has no configured profile.")

    @property
    def model_pool(self) -> tuple[str, ...]:
        """Compatibility metadata only; Responses never silently changes models."""
        return tuple(profile.id for profile in self.profiles)


class OpenAIModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    schema_version: Literal[1] = 1
    model: str


class OpenAIModelCatalog:
    def __init__(self, config: OpenAICloudConfig, selection_path: Path | None = None):
        self.config = config
        self._store = JsonStore(selection_path) if selection_path is not None else None
        self.current_id = config.default_model
        stored = self._store.load() if self._store is not None else None
        if stored is not None:
            self.current_id = OpenAIModelSelection.model_validate(stored).model
        config.profile(self.current_id)

    @property
    def current_profile(self) -> OpenAIModelProfile:
        return self.config.profile(self.current_id)

    def select(self, model_id: str) -> None:
        self.config.profile(model_id)
        if self._store is not None:
            self._store.save(OpenAIModelSelection(model=model_id).model_dump())
        self.current_id = model_id
