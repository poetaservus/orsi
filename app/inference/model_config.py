from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import load_json
from app.paths import PATHS


@dataclass(frozen=True)
class ContextSelection:
    length: int
    reason: str
    native_context: int | None
    gpu_total_mib: int | None
    gpu_free_mib: int | None


def detect_nvidia_memory_mib() -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi.exe", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        devices = []
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                total, free = (int(value.strip()) for value in line.split(",", 1))
                devices.append((total, free))
        return max(devices, key=lambda value: value[1]) if devices else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_path: str
    context_length: int | Literal["auto"] = "auto"
    minimum_context_length: int = Field(4096, ge=512)
    maximum_context_length: int = Field(32768, ge=512)
    cpu_context_length: int = Field(8192, ge=512)
    context_vram_fraction: float = Field(0.80, gt=0, le=1)
    context_free_vram_fraction: float = Field(0.90, gt=0, le=1)
    context_model_size_multiplier: float = Field(1.20, ge=1, le=3)
    context_fixed_reserve_mib: int = Field(1024, ge=0)
    estimated_kv_bytes_per_token: int = Field(262144, ge=16384)
    temperature: float = Field(0.1, ge=0, le=2)
    max_tokens: int = Field(512, ge=32)
    gpu_layers: int = -1

    @model_validator(mode="after")
    def validate_context_limits(self):
        if self.maximum_context_length < self.minimum_context_length:
            raise ValueError("maximum_context_length must be at least minimum_context_length.")
        return self

    @property
    def resolved_model_path(self) -> Path:
        path = Path(self.model_path)
        return path if path.is_absolute() else PATHS.root / path

    def select_context(self, *, native_context: int | None, gpu_offload_available: bool,
                       gpu_memory_mib: tuple[int, int] | None = None,
                       model_size_bytes: int | None = None) -> ContextSelection:
        native = native_context if native_context and native_context > 0 else None
        upper = min(self.maximum_context_length, native or self.maximum_context_length)
        lower = min(self.minimum_context_length, upper)
        if isinstance(self.context_length, int):
            selected = max(512, min(self.context_length, upper))
            return ContextSelection(selected, "fixed configuration", native, None, None)

        memory = gpu_memory_mib if gpu_memory_mib is not None else detect_nvidia_memory_mib()
        if not gpu_offload_available or not memory:
            selected = max(lower, min(self.cpu_context_length, upper))
            reason = "CPU/default profile" if not gpu_offload_available else "GPU memory unavailable; safe fallback"
            return ContextSelection(selected, reason, native, None, None)

        total_mib, free_mib = memory
        usable_mib = min(total_mib * self.context_vram_fraction,
                         free_mib * self.context_free_vram_fraction)
        model_bytes = model_size_bytes if model_size_bytes is not None else self.resolved_model_path.stat().st_size
        model_mib = model_bytes / (1024 * 1024)
        context_mib = max(0, usable_mib - model_mib * self.context_model_size_multiplier
                          - self.context_fixed_reserve_mib)
        estimated_capacity = int(context_mib * 1024 * 1024 / self.estimated_kv_bytes_per_token)
        allowed = max(lower, min(upper, estimated_capacity))
        selected = lower
        while selected * 2 <= allowed:
            selected *= 2
        return ContextSelection(selected, "adaptive GPU memory profile", native, total_mib, free_mib)


def load_model_config() -> ModelConfig:
    return ModelConfig.model_validate(load_json(PATHS.config / "model.json"))
