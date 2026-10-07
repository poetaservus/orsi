"""A qualified, content-addressed model/projector pair; selection remains explicit."""
from hashlib import sha256
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from app.settings.paths import PATHS


class LocalVisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    projector_path: str = Field(min_length=1, max_length=1024)
    projector_size_bytes: int = Field(gt=0)
    projector_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_size_bytes: int = Field(gt=0)
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    max_image_tokens: int = Field(default=4096, ge=8, le=4096)

    @property
    def resolved_projector_path(self):
        path = Path(self.projector_path)
        return path if path.is_absolute() else PATHS.root / path


_lock = RLock()
_verified = {}


def verify_vision_pair(config):
    """Before starting inference, verify both identities, including direct callers."""
    vision = config.vision
    if vision is None:
        return
    from app.settings.local_models import read_model_metadata
    with _lock:
        for path, size, digest in ((config.resolved_model_path, vision.model_size_bytes, vision.model_sha256),
                                  (vision.resolved_projector_path, vision.projector_size_bytes, vision.projector_sha256)):
            try:
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, digest)
                if stat.st_size != size:
                    raise ValueError("Vision model/projector size mismatch.")
                if _verified.get(str(path.resolve())) != signature:
                    h = sha256()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                            h.update(chunk)
                    after = path.stat()
                    if h.hexdigest() != digest or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != signature[:3]:
                        raise ValueError("Vision model/projector identity mismatch.")
                    _verified[str(path.resolve())] = signature
            except OSError as exc:
                raise ValueError("The matching vision model/projector is missing or unreadable.") from exc
        model = read_model_metadata(config.resolved_model_path)
        projector = read_model_metadata(vision.resolved_projector_path)
        if (model.get("general.architecture") != "qwen3vl"
                or projector.get("general.type") != "mmproj"
                or projector.get("clip.projector_type") != "qwen3vl_merger"
                or projector.get("clip.has_vision_encoder") is not True
                or projector.get("clip.vision.projection_dim") != model.get("qwen3vl.embedding_length")):
            raise ValueError("The vision projector is incompatible with this model.")
