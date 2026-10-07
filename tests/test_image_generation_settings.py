import pytest
from pydantic import ValidationError
from app.settings.images import ImageGenerationSettings, ImageSettingsStore


def test_image_settings_are_separate_and_restore(tmp_path):
    defaults = ImageGenerationSettings()
    store = ImageSettingsStore(defaults, tmp_path / "images.json")
    store.select(defaults.model_copy(update={"size": "1024x1536", "quality": "low"}))
    assert ImageSettingsStore(defaults, tmp_path / "images.json").current.size == "1024x1536"
    assert defaults.size == "1024x1024"
    assert store.current.tool("gpt-6-luna")["model"] == defaults.model
    with pytest.raises(ValueError):
        defaults.tool("unsupported")


@pytest.mark.parametrize("update", [{"model": "unknown"}, {"size": "0x0"}, {"quality": "unknown"}, {"output_format": "bmp"}])
def test_invalid_image_settings_are_rejected(update):
    with pytest.raises(ValidationError):
        ImageGenerationSettings.model_validate(update)
