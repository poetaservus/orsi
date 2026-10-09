"""Image tool defaults, independent of chat model profiles and sampling."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.state.storage import JsonStore


class ImageGenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    model: Literal["gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"] = "gpt-image-2.5-flare"
    size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024"
    quality: Literal["auto", "low", "medium", "high"] = "medium"
    output_format: Literal["png", "jpeg", "webp"] = "png"

    def tool(self, cloud_model):
        # These are the application's explicit Responses profiles. Account access
        # is only established by a real request, never inferred from this list.
        if cloud_model not in {"gpt-6-luna", "gpt-6.1-sol"}:
            raise ValueError("This cloud model does not support O.R.S.I. image generation.")
        return {"type": "image_generation", **self.model_dump(), "partial_images": 0}


class ImageSettingsStore:
    def __getattribute__(self, name):
        if name == "current":
            from app.vault.session import PersonalPath
            store = object.__getattribute__(self, "store")
            if store is not None and isinstance(store.path, PersonalPath):
                store.path.session.require_active()
        return object.__getattribute__(self, name)

    def __init__(self, defaults, path: Path | None = None):
        self.store = JsonStore(path) if path is not None else None
        self.current = defaults
        if self.store is not None:
            value = self.store.load()
            if value is not None:
                self.current = ImageGenerationSettings.model_validate(value)

    def select(self, settings):
        settings = ImageGenerationSettings.model_validate(settings)
        if self.store is not None:
            self.store.save(settings.model_dump(mode="json"))
        self.current = settings
