"""Bounded GGUF discovery and complete, independent local-model profiles."""
from dataclasses import dataclass
from pathlib import Path
import struct

from app.settings.model import ModelConfig, detect_nvidia_memory_mib
from app.state.storage import JsonStore


_SCALARS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f",
            7: "?", 10: "Q", 11: "q", 12: "d"}
_SUPPORTED = {"qwen2", "qwen3", "qwen3vl"}
_METADATA_LIMIT = 64 * 1024 * 1024


def read_model_metadata(path: Path) -> dict:
    """Read metadata only, skipping token arrays and never loading model tensors."""
    with path.open("rb") as stream:
        size = path.stat().st_size

        def read(count):
            if count < 0 or stream.tell() + count > min(size, _METADATA_LIMIT):
                raise ValueError("GGUF metadata exceeds its size limit or is truncated.")
            result = stream.read(count)
            if len(result) != count:
                raise ValueError("Truncated GGUF metadata.")
            return result

        def number(fmt):
            return struct.unpack("<" + fmt, read(struct.calcsize("<" + fmt)))[0]

        def string(keep=True):
            count = number("Q")
            if count > 1024 * 1024:
                raise ValueError("GGUF metadata string is too large.")
            if keep:
                return read(count).decode("utf-8")
            if stream.tell() + count > min(size, _METADATA_LIMIT):
                raise ValueError("Truncated GGUF metadata.")
            stream.seek(count, 1)

        def value(kind, keep, depth=0):
            if depth > 2:
                raise ValueError("Unsupported nested GGUF metadata.")
            if kind == 8:
                return string(keep)
            if kind == 9:
                subtype, count = number("I"), number("Q")
                if count > 1_000_000:
                    raise ValueError("GGUF metadata array is too large.")
                for _ in range(count):
                    value(subtype, False, depth + 1)
                return None
            if kind not in _SCALARS:
                raise ValueError("Unknown GGUF metadata type.")
            return number(_SCALARS[kind])

        if read(4) != b"GGUF" or number("I") not in {2, 3}:
            raise ValueError("Not a supported GGUF file.")
        number("Q")  # tensor count; tensor data is not needed for discovery
        count = number("Q")
        if count > 10_000:
            raise ValueError("Too many GGUF metadata fields.")
        metadata = {}
        for _ in range(count):
            key = string()
            keep = not key.startswith("tokenizer.") or key == "tokenizer.chat_template"
            item = value(number("I"), keep)
            if keep:
                metadata[key] = item
        return metadata


@dataclass(frozen=True)
class LocalModel:
    id: str
    name: str
    path: Path
    architecture: str
    native_context: int
    kv_bytes_per_token: int

    @property
    def text_only(self):
        return self.architecture == "qwen3vl"

    @property
    def compatibility_note(self) -> str:
        if self.architecture == "qwen3vl":
            return "Experimental: file editing may fail. No image input."
        return "Text and tools"


def inspect_model(path: Path) -> LocalModel:
    metadata = read_model_metadata(path)
    architecture = metadata.get("general.architecture")
    if architecture not in _SUPPORTED:
        raise ValueError("This model architecture has no ORSI profile yet.")
    template = metadata.get("tokenizer.chat_template", "")
    if not isinstance(template, str) or not all(marker in template for marker in ("tools", "tool_call")):
        raise ValueError("This model needs an embedded tool-calling chat template.")

    def integer(key, default=None):
        result = metadata.get(f"{architecture}.{key}", default)
        if type(result) is not int or not 0 < result <= 1_048_576:
            raise ValueError("Invalid model dimensions or context metadata.")
        return result

    heads = integer("attention.head_count")
    head_size = integer("embedding_length") // heads
    kv = integer("block_count") * integer("attention.head_count_kv") * (
        integer("attention.key_length", head_size) + integer("attention.value_length", head_size)
    ) * 2  # FP16 keys and values
    name = str(metadata.get("general.name", path.stem))[:100]
    if metadata.get("general.file_type") == 15:
        name += " · Q4_K_M"
    return LocalModel(path.name, name, path, architecture, integer("context_length"), kv)


class LocalModelCatalog:
    def __init__(self, models_directory: Path, config_path: Path, current: ModelConfig):
        self.models_directory = models_directory
        self.config_path = config_path
        self.current_config = current
        self.models = []
        self.unavailable = []
        for path in sorted(models_directory.glob("*.gguf")):
            try:
                self.models.append(inspect_model(path))
            except (OSError, ValueError, UnicodeError, struct.error) as exc:
                self.unavailable.append((path.name, str(exc)))

    @property
    def current_id(self):
        return Path(self.current_config.model_path).name

    def configuration(self, model_id: str) -> ModelConfig:
        entry = next((item for item in self.models if item.id == model_id), None)
        if entry is None:
            raise ValueError("Select an available local model.")
        model = inspect_model(entry.path)  # detect removed/replaced/corrupted metadata
        gpu = detect_nvidia_memory_mib()
        maximum = min(16384, model.native_context)
        config = ModelConfig(
            model_path=str(model.path.resolve()), context_length="auto",
            minimum_context_length=min(4096, maximum), maximum_context_length=maximum,
            cpu_context_length=min(4096, maximum), estimated_kv_bytes_per_token=model.kv_bytes_per_token,
            gpu_layers=-1 if gpu else 0, max_tokens=4096,
            temperature=0.2 if model.architecture == "qwen3vl" else 0.1,
            top_p=0.9 if model.architecture == "qwen3vl" else 0.95,
            top_k=40, min_p=0.0 if model.architecture == "qwen3vl" else 0.05,
            repeat_penalty=1.0, presence_penalty=0.0, cache_type="f16",
        )
        selection = config.select_context(native_context=model.native_context,
                                          gpu_offload_available=gpu is not None,
                                          gpu_memory_mib=gpu)
        # Keep the response reserve proportional if a CPU/memory fallback reduces context.
        return config.model_copy(update={"context_length": selection.length,
                                         "max_tokens": min(4096, selection.length // 4)})

    def save(self, config: ModelConfig):
        data = config.model_dump()
        try:
            data["model_path"] = config.resolved_model_path.relative_to(
                self.config_path.parent.parent.resolve()).as_posix()
        except ValueError:
            pass
        JsonStore(self.config_path).save(data)
        self.current_config = config
