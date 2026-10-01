"""Bounded GGUF discovery and complete, independent local-model profiles."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import logging
import struct

from app.settings.model import ModelConfig, detect_nvidia_memory_mib
from app.settings.model_profiles import LocalModelProfile, LocalModelProfiles
from app.settings.loader import load_json
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
    def __init__(self, models_directory: Path, config_path: Path, current: ModelConfig,
                 *, selection_path: Path | None = None):
        self.models_directory = models_directory
        self.config_path = config_path
        self.selection_path = selection_path or config_path.parent.parent / "state" / "local_model_selection_v1.json"
        values = load_json(config_path, default={})
        self.profiles = LocalModelProfiles.model_validate(values) if "profiles" in values else None
        self.profiles_sha256 = hashlib.sha256(self.profiles.model_dump_json().encode()).hexdigest() \
            if self.profiles else None
        self._legacy_config = current
        self._identities = {}
        self._resolutions = {}
        self.current_config = current
        self.models = []
        self.unavailable = []
        for path in sorted(models_directory.glob("*.gguf")):
            try:
                self.models.append(inspect_model(path))
            except (OSError, ValueError, UnicodeError, struct.error) as exc:
                self.unavailable.append((path.name, str(exc)))

    def selected_id(self) -> str:
        """Invalid saved selection falls back to the versioned default, without rewriting it."""
        default = self.profiles.default_model_id if self.profiles else self.current_id
        try:
            saved = JsonStore(self.selection_path).load(default={})
            if (isinstance(saved, dict) and set(saved) == {"schema_version", "model_id"}
                    and saved["schema_version"] == 1
                    and any(item.id == saved["model_id"] for item in self.models)):
                return saved["model_id"]
        except (OSError, ValueError):
            logging.getLogger(__name__).warning("Saved local selection is invalid; using the default profile.")
        return default

    def profile(self, model: LocalModel) -> LocalModelProfile:
        accepted = self.profiles.get(model.id) if self.profiles else None
        if accepted is not None:
            return accepted
        maximum = min(16384, model.native_context)
        # Old flat configuration remains readable, but selection never writes it.
        legacy = self._legacy_config if model.id == Path(self._legacy_config.model_path).name else None
        configuration = legacy if legacy and isinstance(legacy.context_length, int) else ModelConfig(
            model_path=str(model.path.resolve()), context_length=maximum,
            minimum_context_length=min(4096, maximum), maximum_context_length=maximum,
            cpu_context_length=min(4096, maximum), estimated_kv_bytes_per_token=model.kv_bytes_per_token,
            max_tokens=min(4096, maximum // 2),
            temperature=0.2 if model.architecture == "qwen3vl" else 0.1,
            top_p=0.9 if model.architecture == "qwen3vl" else 0.95,
            min_p=0.0 if model.architecture == "qwen3vl" else 0.05,
        )
        return LocalModelProfile(model_id=model.id, qualification="unqualified",
                                 architecture=model.architecture, configuration=configuration,
                                 cpu_max_tokens=min(1024, configuration.cpu_context_length // 2))

    def identity(self, model: LocalModel) -> dict:
        stat = model.path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        cached = self._identities.get(model.id)
        if cached is None or cached[0] != signature:
            digest = hashlib.sha256()
            with model.path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
            if model.path.stat().st_mtime_ns != signature[1]:
                raise ValueError("The model changed during identity verification.")
            cached = (signature, digest.hexdigest())
            self._identities[model.id] = cached
        return {"model_id": model.id, "architecture": model.architecture,
                "size_bytes": signature[0], "sha256": cached[1]}

    def diagnostic(self) -> dict | None:
        return self._resolutions.get(self.current_id)

    @property
    def current_id(self):
        return Path(self.current_config.model_path).name

    def configuration(self, model_id: str) -> ModelConfig:
        entry = next((item for item in self.models if item.id == model_id), None)
        if entry is None:
            raise ValueError("Select an available local model.")
        model = inspect_model(entry.path)  # detect removed/replaced/corrupted metadata
        profile = self.profile(model)
        identity = self.identity(model)
        if (model.architecture != profile.architecture
                or profile.size_bytes is not None and identity["size_bytes"] != profile.size_bytes
                or profile.sha256 is not None and identity["sha256"] != profile.sha256):
            raise ValueError("This model file does not match its versioned profile.")
        gpu = detect_nvidia_memory_mib()
        target = profile.configuration
        maximum = min(target.context_length, target.maximum_context_length, model.native_context)
        config = target.model_copy(update={"model_path": str(model.path.resolve()),
            "context_length": "auto", "maximum_context_length": maximum,
            "minimum_context_length": min(target.minimum_context_length, maximum),
            "estimated_kv_bytes_per_token": model.kv_bytes_per_token})
        selection = config.select_context(native_context=model.native_context,
                                          gpu_offload_available=gpu is not None and target.gpu_layers != 0,
                                          gpu_memory_mib=gpu, model_size_bytes=identity["size_bytes"])
        cpu = not selection.gpu_offload
        effective = config.model_copy(update={"context_length": selection.length,
            "gpu_layers": 0 if cpu else target.gpu_layers,
            "max_tokens": min(profile.cpu_max_tokens if cpu else target.max_tokens, selection.length // 2)})
        estimated_mib = (identity["size_bytes"] / 1048576 * config.context_model_size_multiplier
                         + config.context_fixed_reserve_mib
                         + selection.length * model.kv_bytes_per_token / 1048576)
        self._resolutions[model_id] = {
            **identity, "qualification": profile.qualification,
            "profiles_sha256": self.profiles_sha256,
            "native_context": model.native_context,
            "target": {"context_length": target.context_length, "max_response_tokens": target.max_tokens},
            "effective": {"context_length": effective.context_length,
                          "max_response_tokens": effective.max_tokens, "gpu_layers": effective.gpu_layers,
                          "cache_type": effective.cache_type, **effective.sampling_parameters()},
            "selection_reason": selection.reason,
            "gpu_before_load_mib": {"total": gpu[0], "free": gpu[1]} if gpu else None,
            "estimated_allocation_mib": round(estimated_mib, 2) if not cpu else None,
            "memory_guard": {key: getattr(config, key) for key in (
                "context_vram_fraction", "context_free_vram_fraction", "context_model_size_multiplier",
                "context_fixed_reserve_mib", "estimated_kv_bytes_per_token")},
        }
        return effective

    def save(self, config: ModelConfig):
        JsonStore(self.selection_path).save({"schema_version": 1,
                                           "model_id": Path(config.model_path).name})
        self.current_config = config
